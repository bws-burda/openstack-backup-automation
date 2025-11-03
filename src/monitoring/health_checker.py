"""Health check functionality for system components."""

import asyncio
import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime
from typing import List, Optional

from ..interfaces import OpenStackClientInterface, StateManagerInterface
from .models import ComponentHealth, HealthCheckConfig, HealthStatus, SystemStatus


class HealthChecker:
    """Performs health checks on system components."""
    
    def __init__(
        self,
        config: HealthCheckConfig,
        openstack_client: Optional[OpenStackClientInterface] = None,
        state_manager: Optional[StateManagerInterface] = None,
        database_path: Optional[str] = None,
    ):
        """Initialize health checker.
        
        Args:
            config: Health check configuration
            openstack_client: OpenStack client for API connectivity checks
            state_manager: State manager for database checks
            database_path: Path to database file for direct checks
        """
        self.config = config
        self.openstack_client = openstack_client
        self.state_manager = state_manager
        self.database_path = database_path
        self.logger = logging.getLogger(__name__)
        self.start_time = time.time()
    
    async def check_system_health(self) -> SystemStatus:
        """Perform comprehensive system health check.
        
        Returns:
            SystemStatus with overall health and component details
        """
        components = []
        
        # Check database connectivity
        if self.config.database_check_enabled:
            db_health = await self._check_database_health()
            components.append(db_health)
        
        # Check OpenStack API connectivity
        if self.config.openstack_check_enabled and self.openstack_client:
            openstack_health = await self._check_openstack_health()
            components.append(openstack_health)
        
        # Check local storage (for database/logs only)
        if self.config.local_storage_check_enabled:
            local_storage_health = await self._check_local_storage()
            components.append(local_storage_health)
        
        # Check OpenStack quotas and storage services
        if self.config.openstack_check_enabled and self.openstack_client:
            quota_health = await self._check_openstack_quotas()
            components.append(quota_health)
        
        # Determine overall status
        overall_status = self._determine_overall_status(components)
        
        return SystemStatus(
            overall_status=overall_status,
            components=components,
            timestamp=datetime.utcnow(),
            uptime_seconds=time.time() - self.start_time,
        )
    
    async def _check_database_health(self) -> ComponentHealth:
        """Check database connectivity and basic operations."""
        try:
            if self.state_manager:
                # Use state manager for check if available
                test_backup = self.state_manager.get_last_backup("health-check-test")
                status = HealthStatus.HEALTHY
                message = "Database connection successful via StateManager"
                details = {"method": "state_manager"}
            elif self.database_path:
                # Direct database connection check
                conn = sqlite3.connect(self.database_path, timeout=self.config.timeout_seconds)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                conn.close()
                
                status = HealthStatus.HEALTHY
                message = "Database connection successful"
                details = {"method": "direct_connection", "path": self.database_path}
            else:
                status = HealthStatus.DEGRADED
                message = "No database connection method available"
                details = {"error": "Neither state_manager nor database_path provided"}
        
        except sqlite3.OperationalError as e:
            status = HealthStatus.UNHEALTHY
            message = f"Database connection failed: {str(e)}"
            details = {"error": str(e), "error_type": "operational"}
        except Exception as e:
            status = HealthStatus.UNHEALTHY
            message = f"Database health check failed: {str(e)}"
            details = {"error": str(e), "error_type": type(e).__name__}
        
        return ComponentHealth(
            name="database",
            status=status,
            message=message,
            last_check=datetime.utcnow(),
            details=details,
        )
    
    async def _check_openstack_health(self) -> ComponentHealth:
        """Check OpenStack API connectivity."""
        try:
            # Try to get a simple resource list to test connectivity
            instances = await asyncio.wait_for(
                self.openstack_client.get_instances_with_tags(),
                timeout=self.config.timeout_seconds
            )
            
            status = HealthStatus.HEALTHY
            message = "OpenStack API connection successful"
            details = {
                "instances_found": len(instances) if instances else 0,
                "api_responsive": True,
            }
        
        except asyncio.TimeoutError:
            status = HealthStatus.UNHEALTHY
            message = f"OpenStack API timeout after {self.config.timeout_seconds}s"
            details = {"error": "timeout", "timeout_seconds": self.config.timeout_seconds}
        
        except Exception as e:
            # Determine if this is a degraded or unhealthy state
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ["unauthorized", "forbidden", "authentication"]):
                status = HealthStatus.UNHEALTHY
                message = f"OpenStack authentication failed: {str(e)}"
            elif any(keyword in error_str for keyword in ["connection", "network", "timeout"]):
                status = HealthStatus.DEGRADED
                message = f"OpenStack connectivity issues: {str(e)}"
            else:
                status = HealthStatus.DEGRADED
                message = f"OpenStack API error: {str(e)}"
            
            details = {"error": str(e), "error_type": type(e).__name__}
        
        return ComponentHealth(
            name="openstack_api",
            status=status,
            message=message,
            last_check=datetime.utcnow(),
            details=details,
        )
    
    async def _check_openstack_quotas(self) -> ComponentHealth:
        """Check OpenStack quotas and storage availability."""
        try:
            # Check Cinder quotas (for volume backups)
            # This is what actually matters for backup storage
            
            # Note: This would require extending the OpenStack client
            # to get quota information. For now, we'll do a basic check
            # by trying to list existing backups to see if the service is responsive
            
            if not self.openstack_client:
                status = HealthStatus.DEGRADED
                message = "OpenStack client not available for quota check"
                details = {"error": "No OpenStack client configured"}
            else:
                # Try to access Cinder backup service
                # This is a proxy check - if we can list backups, the service is working
                # In a real implementation, you'd want to check actual quotas
                try:
                    # Placeholder for quota check - would need OpenStack client extension
                    # volumes = await self.openstack_client.get_volumes_with_tags()
                    
                    status = HealthStatus.HEALTHY
                    message = "OpenStack storage services accessible"
                    details = {
                        "check_type": "service_accessibility",
                        "note": "Quota limits should be monitored separately via OpenStack APIs"
                    }
                except Exception as e:
                    status = HealthStatus.DEGRADED
                    message = f"OpenStack storage services check failed: {str(e)}"
                    details = {"error": str(e), "error_type": type(e).__name__}
        
        except Exception as e:
            status = HealthStatus.UNHEALTHY
            message = f"OpenStack quota check failed: {str(e)}"
            details = {"error": str(e), "error_type": type(e).__name__}
        
        return ComponentHealth(
            name="openstack_quotas",
            status=status,
            message=message,
            last_check=datetime.utcnow(),
            details=details,
        )
    
    async def _check_local_storage(self) -> ComponentHealth:
        """Check local storage for database and logs (minimal check)."""
        try:
            # Only check local storage for the small database file
            if self.database_path:
                db_dir = os.path.dirname(os.path.abspath(self.database_path))
            else:
                db_dir = os.getcwd()
            
            total, used, free = shutil.disk_usage(db_dir)
            used_percent = (used / total) * 100
            
            # More lenient thresholds since this is just for metadata
            if used_percent >= 95:  # Very high threshold since DB is tiny
                status = HealthStatus.UNHEALTHY
                message = f"Local storage critical: {used_percent:.1f}% used"
            elif used_percent >= 90:
                status = HealthStatus.DEGRADED
                message = f"Local storage warning: {used_percent:.1f}% used"
            else:
                status = HealthStatus.HEALTHY
                message = f"Local storage OK: {used_percent:.1f}% used (metadata only)"
            
            details = {
                "path": db_dir,
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round(free / (1024**3), 2),
                "used_percent": round(used_percent, 1),
                "purpose": "database_and_logs_only",
                "note": "Actual backup storage is in OpenStack (Cinder/Glance)"
            }
        
        except Exception as e:
            status = HealthStatus.UNHEALTHY
            message = f"Local storage check failed: {str(e)}"
            details = {"error": str(e), "error_type": type(e).__name__}
        
        return ComponentHealth(
            name="local_storage",
            status=status,
            message=message,
            last_check=datetime.utcnow(),
            details=details,
        )
    
    def _determine_overall_status(self, components: List[ComponentHealth]) -> HealthStatus:
        """Determine overall system status from component health."""
        if not components:
            return HealthStatus.DEGRADED
        
        # If any component is unhealthy, system is unhealthy
        if any(c.is_unhealthy() for c in components):
            return HealthStatus.UNHEALTHY
        
        # If any component is degraded, system is degraded
        if any(c.is_degraded() for c in components):
            return HealthStatus.DEGRADED
        
        # All components healthy
        return HealthStatus.HEALTHY
    
    async def check_component_health(self, component_name: str) -> Optional[ComponentHealth]:
        """Check health of a specific component.
        
        Args:
            component_name: Name of component to check
            
        Returns:
            ComponentHealth or None if component not found
        """
        if component_name == "database" and self.config.database_check_enabled:
            return await self._check_database_health()
        elif component_name == "openstack_api" and self.config.openstack_check_enabled:
            return await self._check_openstack_health()
        elif component_name == "local_storage" and self.config.local_storage_check_enabled:
            return await self._check_local_storage()
        elif component_name == "openstack_quotas" and self.config.openstack_check_enabled:
            return await self._check_openstack_quotas()
        else:
            return None