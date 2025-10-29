"""OpenStack API client implementation."""

import asyncio
import logging
import random
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar

import openstack
from openstack.connection import Connection
from openstack.exceptions import HttpException, SDKException

from ..config.models import AuthMethod, OpenStackCredentials
from ..interfaces import OpenStackClientInterface

T = TypeVar('T')


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class TokenExpiredError(Exception):
    """Raised when token has expired."""
    pass


class APIError(Exception):
    """Raised when API operations fail."""
    pass


class RetryableError(Exception):
    """Raised when an operation can be retried."""
    pass


class OpenStackClient(OpenStackClientInterface):
    """OpenStack API client for backup operations with automatic token management."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.connection: Optional[Connection] = None
        self._authenticated = False
        self._credentials: Optional[OpenStackCredentials] = None
        self._token_expires_at: Optional[float] = None
        self._auth_lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)
        
        # Token refresh buffer - refresh token 5 minutes before expiry
        self._token_refresh_buffer = 300
        
        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Connection health tracking
        self._last_successful_call: Optional[float] = None
        self._consecutive_failures = 0

    def authenticate(self, credentials: OpenStackCredentials) -> bool:
        """Authenticate with OpenStack and store credentials for token renewal."""
        try:
            self._credentials = credentials
            return self._perform_authentication()
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            self._authenticated = False
            return False

    def _perform_authentication(self) -> bool:
        """Perform the actual authentication with stored credentials."""
        if not self._credentials:
            raise AuthenticationError("No credentials available for authentication")

        try:
            auth_args = {
                "auth_url": self._credentials.auth_url,
                "project_name": self._credentials.project_name,
                "project_domain_name": self._credentials.project_domain_name,
            }

            if self._credentials.auth_method == AuthMethod.APPLICATION_CREDENTIAL:
                if not self._credentials.application_credential_id or not self._credentials.application_credential_secret:
                    raise AuthenticationError("Application credential ID and secret are required")
                
                auth_args.update({
                    "application_credential_id": self._credentials.application_credential_id,
                    "application_credential_secret": self._credentials.application_credential_secret,
                })
                self.logger.debug("Using application credential authentication")
                
            elif self._credentials.auth_method == AuthMethod.PASSWORD:
                if not self._credentials.username or not self._credentials.password:
                    raise AuthenticationError("Username and password are required")
                
                auth_args.update({
                    "username": self._credentials.username,
                    "password": self._credentials.password,
                    "user_domain_name": self._credentials.user_domain_name,
                })
                self.logger.debug("Using username/password authentication")
            else:
                raise AuthenticationError(f"Unsupported authentication method: {self._credentials.auth_method}")

            # Create connection
            self.connection = openstack.connect(**auth_args)

            # Test authentication by making a simple API call
            self.connection.authorize()
            
            # Store token expiration time if available
            auth_ref = getattr(self.connection.session.auth, 'auth_ref', None)
            if auth_ref and hasattr(auth_ref, 'expires'):
                # Convert to timestamp
                self._token_expires_at = auth_ref.expires.timestamp()
                self.logger.debug(f"Token expires at: {auth_ref.expires}")
            else:
                # Default to 1 hour if we can't determine expiration
                self._token_expires_at = time.time() + 3600
                self.logger.debug("Could not determine token expiration, using 1 hour default")

            self._authenticated = True
            self.logger.info("Successfully authenticated with OpenStack")
            return True

        except HttpException as e:
            if e.status_code == 401:
                raise AuthenticationError(f"Invalid credentials: {e}")
            elif e.status_code == 403:
                raise AuthenticationError(f"Access denied: {e}")
            else:
                raise AuthenticationError(f"HTTP error during authentication: {e}")
        except SDKException as e:
            raise AuthenticationError(f"OpenStack SDK error: {e}")
        except Exception as e:
            raise AuthenticationError(f"Unexpected error during authentication: {e}")

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid authentication token, refreshing if necessary."""
        async with self._auth_lock:
            if not self._authenticated or not self.connection:
                if not self._credentials:
                    raise AuthenticationError("No credentials available")
                self._perform_authentication()
                return

            # Check if token is about to expire
            if self._token_expires_at and time.time() >= (self._token_expires_at - self._token_refresh_buffer):
                self.logger.info("Token is about to expire, refreshing authentication")
                try:
                    self._perform_authentication()
                except Exception as e:
                    self.logger.error(f"Failed to refresh authentication: {e}")
                    raise TokenExpiredError(f"Failed to refresh expired token: {e}")

    def is_authenticated(self) -> bool:
        """Check if client is currently authenticated."""
        return self._authenticated and self.connection is not None

    def get_token_expiry(self) -> Optional[float]:
        """Get token expiration timestamp."""
        return self._token_expires_at

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        if isinstance(error, HttpException):
            # Retry on server errors, rate limits, and temporary network issues
            retryable_status_codes = {500, 502, 503, 504, 429}
            return error.status_code in retryable_status_codes
        
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True
            
        # Token expiration should trigger re-authentication, not retry
        if isinstance(error, TokenExpiredError):
            return False
            
        return False

    async def _exponential_backoff(self, attempt: int) -> None:
        """Implement exponential backoff with jitter."""
        if attempt == 0:
            return
            
        # Exponential backoff: base_delay * (2 ^ attempt) + random jitter
        delay = self.retry_delay * (2 ** (attempt - 1))
        jitter = random.uniform(0, delay * 0.1)  # 10% jitter
        total_delay = min(delay + jitter, 60)  # Cap at 60 seconds
        
        self.logger.debug(f"Retrying in {total_delay:.2f} seconds (attempt {attempt})")
        await asyncio.sleep(total_delay)

    async def _retry_on_failure(self, operation: Callable[[], T], operation_name: str) -> T:
        """Retry an operation with exponential backoff."""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    await self._exponential_backoff(attempt)
                
                result = await operation()
                
                # Reset failure counter on success
                self._consecutive_failures = 0
                self._last_successful_call = time.time()
                
                return result
                
            except TokenExpiredError:
                # Don't retry token expiration - let it bubble up for re-authentication
                raise
            except Exception as e:
                last_exception = e
                self._consecutive_failures += 1
                
                if not self._is_retryable_error(e):
                    self.logger.error(f"{operation_name} failed with non-retryable error: {e}")
                    break
                
                if attempt < self.max_retries:
                    self.logger.warning(f"{operation_name} failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                else:
                    self.logger.error(f"{operation_name} failed after {self.max_retries + 1} attempts: {e}")
        
        # All retries exhausted
        raise APIError(f"{operation_name} failed after {self.max_retries + 1} attempts: {last_exception}")

    def get_connection_health(self) -> Dict[str, Any]:
        """Get connection health information."""
        return {
            "authenticated": self._authenticated,
            "token_expires_at": self._token_expires_at,
            "last_successful_call": self._last_successful_call,
            "consecutive_failures": self._consecutive_failures,
            "connection_active": self.connection is not None
        }

    async def health_check(self) -> bool:
        """Perform a health check by making a simple API call."""
        try:
            await self._ensure_authenticated()
            
            # Make a simple API call to test connectivity
            list(self.connection.identity.projects(limit=1))
            
            self.logger.debug("Health check passed")
            return True
            
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False

    def reset_connection(self) -> None:
        """Reset the connection state (useful for recovery from persistent errors)."""
        self.logger.info("Resetting OpenStack connection")
        self.connection = None
        self._authenticated = False
        self._token_expires_at = None
        self._consecutive_failures = 0

    async def get_instances_with_tags(
        self, tag_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get instances with optional tag filtering."""
        async def _get_instances():
            await self._ensure_authenticated()
            
            instances = []
            for server in self.connection.compute.servers():
                server_dict = server.to_dict()

                # Get tags - they might be in different places depending on OpenStack version
                tags = getattr(server, "tags", []) or []
                server_dict["tags"] = tags

                # Apply tag filter if specified
                if tag_filter:
                    if not any(tag_filter.upper() in tag.upper() for tag in tags):
                        continue

                instances.append(server_dict)

            self.logger.debug(f"Found {len(instances)} instances with tag filter: {tag_filter}")
            return instances

        try:
            return await self._retry_on_failure(_get_instances, "get_instances_with_tags")
        except HttpException as e:
            if e.status_code == 401:
                raise TokenExpiredError("Token expired while fetching instances")
            raise APIError(f"HTTP error fetching instances: {e}")
        except Exception as e:
            if not isinstance(e, (APIError, TokenExpiredError)):
                raise APIError(f"Error fetching instances: {e}")
            raise

    async def get_volumes_with_tags(
        self, tag_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get volumes with optional tag filtering."""
        async def _get_volumes():
            await self._ensure_authenticated()
            
            volumes = []
            for volume in self.connection.block_storage.volumes():
                volume_dict = volume.to_dict()

                # Get tags and metadata
                tags = getattr(volume, "tags", []) or []
                metadata = getattr(volume, "metadata", {}) or {}

                # Some OpenStack versions store tags in metadata
                volume_dict["tags"] = tags
                volume_dict["metadata"] = metadata

                # Apply tag filter if specified
                if tag_filter:
                    all_tags = tags + list(metadata.keys())
                    if not any(tag_filter.upper() in tag.upper() for tag in all_tags):
                        continue

                volumes.append(volume_dict)

            self.logger.debug(f"Found {len(volumes)} volumes with tag filter: {tag_filter}")
            return volumes

        try:
            return await self._retry_on_failure(_get_volumes, "get_volumes_with_tags")
        except HttpException as e:
            if e.status_code == 401:
                raise TokenExpiredError("Token expired while fetching volumes")
            raise APIError(f"HTTP error fetching volumes: {e}")
        except Exception as e:
            if not isinstance(e, (APIError, TokenExpiredError)):
                raise APIError(f"Error fetching volumes: {e}")
            raise

    async def create_instance_snapshot(self, instance_id: str, name: str) -> str:
        """Create instance snapshot via Nova API."""
        async def _create_snapshot():
            await self._ensure_authenticated()
            
            server = self.connection.compute.get_server(instance_id)
            if not server:
                raise ValueError(f"Instance not found: {instance_id}")

            self.logger.info(f"Creating snapshot '{name}' for instance {instance_id}")
            # Create snapshot (image)
            image = self.connection.compute.create_server_image(server, name)
            self.logger.info(f"Successfully created instance snapshot {image.id}")
            return image.id

        try:
            return await self._retry_on_failure(_create_snapshot, "create_instance_snapshot")
        except HttpException as e:
            if e.status_code == 401:
                raise TokenExpiredError("Token expired while creating instance snapshot")
            elif e.status_code == 404:
                raise ValueError(f"Instance not found: {instance_id}")
            elif e.status_code == 409:
                raise APIError(f"Instance {instance_id} is in an invalid state for snapshot creation")
            else:
                raise APIError(f"HTTP error creating instance snapshot: {e}")
        except ValueError:
            # Don't wrap ValueError in APIError
            raise
        except Exception as e:
            if not isinstance(e, (APIError, TokenExpiredError)):
                raise APIError(f"Failed to create instance snapshot: {e}")
            raise

    async def create_volume_snapshot(self, volume_id: str, name: str) -> str:
        """Create volume snapshot via Cinder API."""
        async def _create_snapshot():
            await self._ensure_authenticated()
            
            volume = self.connection.block_storage.get_volume(volume_id)
            if not volume:
                raise ValueError(f"Volume not found: {volume_id}")

            self.logger.info(f"Creating snapshot '{name}' for volume {volume_id}")
            # Create snapshot
            snapshot = self.connection.block_storage.create_snapshot(
                volume_id=volume_id,
                name=name,
                force=True,  # Allow snapshot of in-use volumes
            )
            self.logger.info(f"Successfully created volume snapshot {snapshot.id}")
            return snapshot.id

        try:
            return await self._retry_on_failure(_create_snapshot, "create_volume_snapshot")
        except HttpException as e:
            if e.status_code == 401:
                raise TokenExpiredError("Token expired while creating volume snapshot")
            elif e.status_code == 404:
                raise ValueError(f"Volume not found: {volume_id}")
            elif e.status_code == 409:
                raise APIError(f"Volume {volume_id} is in an invalid state for snapshot creation")
            else:
                raise APIError(f"HTTP error creating volume snapshot: {e}")
        except ValueError:
            # Don't wrap ValueError in APIError
            raise
        except Exception as e:
            if not isinstance(e, (APIError, TokenExpiredError)):
                raise APIError(f"Failed to create volume snapshot: {e}")
            raise

    async def create_volume_backup(
        self,
        volume_id: str,
        name: str,
        incremental: bool = False,
        parent_id: Optional[str] = None,
    ) -> str:
        """Create volume backup via Cinder API."""
        async def _create_backup():
            await self._ensure_authenticated()
            
            volume = self.connection.block_storage.get_volume(volume_id)
            if not volume:
                raise ValueError(f"Volume not found: {volume_id}")

            backup_type = "incremental" if incremental else "full"
            self.logger.info(f"Creating {backup_type} backup '{name}' for volume {volume_id}")

            # Create backup
            backup_args = {
                "volume_id": volume_id,
                "name": name,
                "force": True,  # Allow backup of in-use volumes
            }

            if incremental and parent_id:
                backup_args["incremental"] = True
                backup_args["parent_id"] = parent_id
                self.logger.debug(f"Incremental backup based on parent: {parent_id}")

            backup = self.connection.block_storage.create_backup(**backup_args)
            self.logger.info(f"Successfully created volume backup {backup.id}")
            return backup.id

        try:
            return await self._retry_on_failure(_create_backup, "create_volume_backup")
        except HttpException as e:
            if e.status_code == 401:
                raise TokenExpiredError("Token expired while creating volume backup")
            elif e.status_code == 404:
                if parent_id:
                    raise ValueError(f"Parent backup not found: {parent_id}")
                else:
                    raise ValueError(f"Volume not found: {volume_id}")
            elif e.status_code == 409:
                raise APIError(f"Volume {volume_id} is in an invalid state for backup creation")
            else:
                raise APIError(f"HTTP error creating volume backup: {e}")
        except ValueError:
            # Don't wrap ValueError in APIError
            raise
        except Exception as e:
            if not isinstance(e, (APIError, TokenExpiredError)):
                raise APIError(f"Failed to create volume backup: {e}")
            raise

    async def delete_snapshot(self, snapshot_id: str, resource_type: str) -> bool:
        """Delete a snapshot."""
        async def _delete_snapshot():
            await self._ensure_authenticated()
            
            self.logger.info(f"Deleting {resource_type} snapshot {snapshot_id}")
            
            if resource_type == "instance":
                # Delete image (instance snapshot)
                self.connection.image.delete_image(snapshot_id)
            elif resource_type == "volume":
                # Delete volume snapshot
                self.connection.block_storage.delete_snapshot(snapshot_id)
            else:
                raise ValueError(f"Unknown resource type: {resource_type}")

            self.logger.info(f"Successfully deleted {resource_type} snapshot {snapshot_id}")
            return True

        try:
            return await self._retry_on_failure(_delete_snapshot, "delete_snapshot")
        except HttpException as e:
            if e.status_code == 401:
                raise TokenExpiredError("Token expired while deleting snapshot")
            elif e.status_code == 404:
                self.logger.warning(f"Snapshot {snapshot_id} not found, may already be deleted")
                return True  # Consider it successful if already deleted
            else:
                self.logger.error(f"HTTP error deleting snapshot: {e}")
                return False
        except ValueError:
            # Don't retry invalid resource types
            self.logger.error(f"Invalid resource type: {resource_type}")
            return False
        except Exception as e:
            if not isinstance(e, (APIError, TokenExpiredError)):
                self.logger.error(f"Error deleting snapshot {snapshot_id}: {e}")
                return False
            raise

    async def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup."""
        async def _delete_backup():
            await self._ensure_authenticated()
            
            self.logger.info(f"Deleting backup {backup_id}")
            self.connection.block_storage.delete_backup(backup_id)
            self.logger.info(f"Successfully deleted backup {backup_id}")
            return True

        try:
            return await self._retry_on_failure(_delete_backup, "delete_backup")
        except HttpException as e:
            if e.status_code == 401:
                raise TokenExpiredError("Token expired while deleting backup")
            elif e.status_code == 404:
                self.logger.warning(f"Backup {backup_id} not found, may already be deleted")
                return True  # Consider it successful if already deleted
            else:
                self.logger.error(f"HTTP error deleting backup: {e}")
                return False
        except Exception as e:
            if not isinstance(e, (APIError, TokenExpiredError)):
                self.logger.error(f"Error deleting backup {backup_id}: {e}")
                return False
            raise

    async def get_backup_status(self, backup_id: str, resource_type: str) -> Optional[str]:
        """Get the status of a backup or snapshot."""
        async def _get_status():
            await self._ensure_authenticated()
            
            if resource_type == "instance":
                # Get image status
                image = self.connection.image.get_image(backup_id)
                status = image.status if image else None
                self.logger.debug(f"Instance snapshot {backup_id} status: {status}")
                return status
            elif resource_type == "volume":
                # Try snapshot first, then backup
                try:
                    snapshot = self.connection.block_storage.get_snapshot(backup_id)
                    status = snapshot.status if snapshot else None
                    self.logger.debug(f"Volume snapshot {backup_id} status: {status}")
                    return status
                except:
                    backup = self.connection.block_storage.get_backup(backup_id)
                    status = backup.status if backup else None
                    self.logger.debug(f"Volume backup {backup_id} status: {status}")
                    return status
            else:
                self.logger.error(f"Unknown resource type: {resource_type}")
                return None

        try:
            return await self._retry_on_failure(_get_status, "get_backup_status")
        except HttpException as e:
            if e.status_code == 401:
                raise TokenExpiredError("Token expired while getting backup status")
            elif e.status_code == 404:
                self.logger.debug(f"Backup/snapshot {backup_id} not found")
                return None
            else:
                self.logger.error(f"HTTP error getting backup status: {e}")
                return None
        except Exception as e:
            if not isinstance(e, (APIError, TokenExpiredError)):
                self.logger.error(f"Error getting backup status for {backup_id}: {e}")
                return None
            raise
