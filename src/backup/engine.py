"""Backup engine implementation."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional

from .models import (
    BackupInfo,
    BackupOperation,
    BackupType,
    OperationResult,
    OperationStatus,
)
from .strategy import BackupStrategy

if TYPE_CHECKING:
    pass


class BackupEngine:
    """Executes backup and snapshot operations with parallel execution support."""

    def __init__(
        self,
        openstack_client: Any,  # OpenStackClientInterface
        state_manager: Any,  # StateManagerInterface
        max_concurrent_operations: int = 5,
        operation_timeout_minutes: int = 60,
        full_backup_interval_days: int = 7,
    ):
        self.openstack_client = openstack_client
        self.state_manager = state_manager
        self.max_concurrent_operations = max_concurrent_operations
        self.operation_timeout_minutes = operation_timeout_minutes
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_operations)
        self.semaphore = asyncio.Semaphore(max_concurrent_operations)
        self.logger = logging.getLogger(__name__)

        # Initialize backup strategy
        self.backup_strategy = BackupStrategy(
            state_manager=state_manager,
            full_backup_interval_days=full_backup_interval_days,
        )

    async def create_instance_snapshot(self, instance_id: str, name: str) -> str:
        """Create a snapshot of an instance."""
        async with self.semaphore:
            return await self.openstack_client.create_instance_snapshot(
                instance_id, name
            )

    async def create_volume_snapshot(self, volume_id: str, name: str) -> str:
        """Create a snapshot of a volume."""
        async with self.semaphore:
            return await self.openstack_client.create_volume_snapshot(volume_id, name)

    async def create_volume_backup(
        self,
        volume_id: str,
        name: str,
        backup_type: str,
        parent_backup_id: Optional[str] = None,
    ) -> str:
        """Create a backup of a volume."""
        async with self.semaphore:
            incremental = backup_type == BackupType.INCREMENTAL.value
            return await self.openstack_client.create_volume_backup(
                volume_id, name, incremental, parent_backup_id
            )

    async def verify_backup_success(
        self, backup_id: str, resource_type: str, timeout_minutes: int = 30
    ) -> bool:
        """Verify backup success with timeout handling."""
        timeout_seconds = timeout_minutes * 60
        start_time = asyncio.get_event_loop().time()

        success_states = {
            "instance": ["active", "available"],
            "volume": ["available", "completed"],
        }
        error_states = ["error", "failed", "deleted"]
        expected_states = success_states.get(resource_type, ["available", "completed"])

        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            try:
                status = await self.openstack_client.get_backup_status(
                    backup_id, resource_type
                )
                if not status:
                    return False

                status_lower = status.lower()
                if status_lower in [s.lower() for s in expected_states]:
                    self.logger.info(f"Backup {backup_id} completed: {status}")
                    return True
                if status_lower in error_states:
                    self.logger.error(f"Backup {backup_id} failed: {status}")
                    return False

                await asyncio.sleep(10)  # Wait 10 seconds before next check
            except Exception as e:
                self.logger.error(f"Error checking backup {backup_id}: {e}")
                await asyncio.sleep(10)

        self.logger.warning(
            f"Backup {backup_id} verification timed out after {timeout_minutes}min"
        )
        return False

    async def execute_parallel_operations(
        self, operations: List[BackupOperation]
    ) -> List[OperationResult]:
        """Execute multiple backup operations in parallel."""
        if not operations:
            return []

        # Sort operations by priority (higher priority first)
        sorted_operations = sorted(operations, key=lambda op: op.priority, reverse=True)

        # Group operations by priority to execute in batches
        priority_groups = []
        current_group = []
        current_priority = None

        for operation in sorted_operations:
            if current_priority is None or operation.priority == current_priority:
                current_group.append(operation)
                current_priority = operation.priority
            else:
                priority_groups.append(current_group)
                current_group = [operation]
                current_priority = operation.priority

        if current_group:
            priority_groups.append(current_group)

        # Execute each priority group in parallel
        all_results = []
        for group in priority_groups:
            # Create tasks for this priority group
            tasks = [self._execute_single_operation(op) for op in group]

            # Execute with timeout
            timeout_seconds = max(op.timeout_minutes for op in group) * 60
            try:
                group_results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout_seconds,
                )

                # Process results and handle exceptions
                for i, result in enumerate(group_results):
                    if isinstance(result, Exception):
                        # Create failed result for exception
                        failed_result = OperationResult(
                            operation=group[i],
                            status=OperationStatus.FAILED,
                            error_message=str(result),
                            started_at=datetime.now(timezone.utc),
                            completed_at=datetime.now(timezone.utc),
                        )
                        all_results.append(failed_result)
                    else:
                        all_results.append(result)

            except asyncio.TimeoutError:
                # Handle timeout for entire group
                for operation in group:
                    timeout_result = OperationResult(
                        operation=operation,
                        status=OperationStatus.TIMEOUT,
                        error_message=f"Operation timed out after {timeout_seconds} seconds",
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc),
                    )
                    all_results.append(timeout_result)

        return all_results

    async def _execute_single_operation(
        self, operation: BackupOperation
    ) -> OperationResult:
        """Execute a single backup operation."""
        result = OperationResult(
            operation=operation,
            status=OperationStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )

        try:
            result.status = OperationStatus.IN_PROGRESS

            # For backup operations (not snapshots), determine the actual backup type and parent
            actual_backup_type = operation.operation_type
            parent_backup_id = operation.parent_backup_id

            if operation.operation_type in [BackupType.FULL, BackupType.INCREMENTAL]:
                # Use backup strategy to determine the appropriate backup type
                if operation.operation_type == BackupType.INCREMENTAL:
                    # Check if we should actually create a full backup instead
                    determined_type = self.determine_backup_type(operation.resource_id)
                    if determined_type == BackupType.FULL:
                        actual_backup_type = BackupType.FULL
                        parent_backup_id = None
                        self.logger.info(
                            f"Switching to full backup for resource {operation.resource_id} "
                            "due to backup strategy requirements"
                        )
                    else:
                        # Get the correct parent backup ID
                        parent_backup_id = self.get_parent_backup_id(
                            operation.resource_id, BackupType.INCREMENTAL
                        )
                        if not parent_backup_id:
                            # No valid parent found, create full backup instead
                            actual_backup_type = BackupType.FULL
                            self.logger.warning(
                                f"No valid parent backup found for resource {operation.resource_id}, "
                                "creating full backup instead"
                            )

            # Generate backup name with timestamp
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            backup_name = (
                f"{operation.resource_name}-{actual_backup_type.value}-{timestamp}"
            )

            # Execute the appropriate backup operation with timeout
            backup_creation_timeout = min(
                operation.timeout_minutes * 60 // 2, 1800
            )  # Max 30 minutes for creation
            backup_id = None

            try:
                if actual_backup_type == BackupType.SNAPSHOT:
                    if operation.resource_type == "instance":
                        backup_id = await asyncio.wait_for(
                            self.create_instance_snapshot(
                                operation.resource_id, backup_name
                            ),
                            timeout=backup_creation_timeout,
                        )
                    elif operation.resource_type == "volume":
                        backup_id = await asyncio.wait_for(
                            self.create_volume_snapshot(
                                operation.resource_id, backup_name
                            ),
                            timeout=backup_creation_timeout,
                        )

                elif actual_backup_type in [BackupType.FULL, BackupType.INCREMENTAL]:
                    if operation.resource_type == "volume":
                        backup_id = await asyncio.wait_for(
                            self.create_volume_backup(
                                operation.resource_id,
                                backup_name,
                                actual_backup_type.value,
                                parent_backup_id,
                            ),
                            timeout=backup_creation_timeout,
                        )
                    else:
                        raise ValueError(
                            f"Backup operations not supported for resource type: {operation.resource_type}"
                        )

            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Backup creation timed out after {backup_creation_timeout} seconds"
                )

            if not backup_id:
                raise RuntimeError("Failed to create backup - no backup ID returned")

            # Verify backup success
            verification_success = await self.verify_backup_success(
                backup_id, operation.resource_type, operation.timeout_minutes
            )

            # Calculate retention days for this backup
            retention_days = self._calculate_retention_days(operation.schedule_tag)

            # Create backup info with actual backup type and parent
            backup_info = BackupInfo(
                backup_id=backup_id,
                resource_id=operation.resource_id,
                resource_type=operation.resource_type,
                backup_type=actual_backup_type,
                parent_backup_id=parent_backup_id,
                verified=verification_success,
                schedule_tag=operation.schedule_tag,
                retention_days=retention_days,
            )

            # Record in state manager
            self.state_manager.record_backup(backup_info)

            # If this is an instance snapshot, find and record related volume snapshots
            if (
                actual_backup_type == BackupType.SNAPSHOT
                and operation.resource_type == "instance"
            ):
                await self._find_and_record_related_volume_snapshots(
                    operation.resource_id,
                    backup_id,
                    backup_name,
                    operation.schedule_tag,
                    retention_days,
                )

            result.status = OperationStatus.COMPLETED
            result.backup_info = backup_info
            result.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            result.status = OperationStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(timezone.utc)

        return result

    def determine_backup_type(self, resource_id: str, full_backup_interval_days: Optional[int] = None) -> BackupType:
        """Determine the appropriate backup type for a resource.

        Args:
            resource_id: ID of the resource
            full_backup_interval_days: Override for full backup interval (from tag FULL{X}). If None, uses config default.

        Returns:
            BackupType indicating whether to create full or incremental backup
        """
        return self.backup_strategy.determine_backup_type(resource_id, full_backup_interval_days)

    def get_parent_backup_id(
        self, resource_id: str, backup_type: BackupType
    ) -> Optional[str]:
        """Get the parent backup ID for incremental backups.

        Args:
            resource_id: ID of the resource
            backup_type: Type of backup being created

        Returns:
            Parent backup ID for incremental backups, None for full backups
        """
        return self.backup_strategy.get_parent_backup_id(resource_id, backup_type)

    def validate_backup_chain_integrity(self, resource_id: str) -> bool:
        """Validate the integrity of the backup chain for a resource.

        Args:
            resource_id: ID of the resource

        Returns:
            True if backup chain is valid, False otherwise
        """
        return self.backup_strategy.validate_backup_chain_integrity(resource_id)

    def get_backup_chain_summary(self, resource_id: str) -> dict:
        """Get a summary of the backup chain for a resource.

        Args:
            resource_id: ID of the resource

        Returns:
            Dictionary with backup chain statistics
        """
        return self.backup_strategy.get_backup_chain_summary(resource_id)

    def should_create_backup(self, resource_id: str, backup_type: BackupType) -> bool:
        """Determine if a backup should be created based on strategy rules.

        Args:
            resource_id: ID of the resource
            backup_type: Type of backup to create

        Returns:
            True if backup should be created, False otherwise
        """
        return self.backup_strategy.should_create_backup(resource_id, backup_type)

    def find_orphaned_backups(self, resource_id: str) -> list:
        """Find backups that reference non-existent parents.

        Args:
            resource_id: ID of the resource

        Returns:
            List of orphaned backup info objects
        """
        return self.backup_strategy.find_orphaned_backups(resource_id)

    def can_safely_delete_backup(self, backup_id: str) -> dict:
        """Check if a backup can be safely deleted without breaking chains.

        Args:
            backup_id: ID of the backup to check

        Returns:
            Dictionary with safety check results
        """
        return self.backup_strategy.can_safely_delete_backup(backup_id)

    def repair_chain_integrity(self, resource_id: str, dry_run: bool = True) -> dict:
        """Attempt to repair backup chain integrity issues.

        Args:
            resource_id: ID of the resource
            dry_run: If True, only report what would be done without making changes

        Returns:
            Dictionary with repair actions taken or planned
        """
        return self.backup_strategy.repair_chain_integrity(resource_id, dry_run)

    def get_chain_roots(self, resource_id: str) -> list:
        """Get all root backups (full backups with no parents) for a resource.

        Args:
            resource_id: ID of the resource

        Returns:
            List of root backup info objects
        """
        return self.backup_strategy.get_chain_roots(resource_id)

    def get_chain_descendants(self, backup_id: str) -> list:
        """Get all descendants (children, grandchildren, etc.) of a backup.

        Args:
            backup_id: ID of the parent backup

        Returns:
            List of descendant backup info objects
        """
        return self.backup_strategy.get_chain_descendants(backup_id)

    def __del__(self):
        """Cleanup executor on destruction."""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)

    def _calculate_retention_days(self, schedule_tag: str) -> Optional[int]:
        """Calculate retention days from schedule tag.

        Args:
            schedule_tag: Schedule tag like 'SNAPSHOT-DAILY-0300-RETAIN14'

        Returns:
            Retention days if found in tag, None otherwise
        """
        if not schedule_tag:
            return None

        import re

        # Look for RETAIN followed by digits
        match = re.search(r"RETAIN(\d+)", schedule_tag)
        if match:
            return int(match.group(1))
        return None

    async def _find_and_record_related_volume_snapshots(
        self,
        instance_id: str,
        instance_snapshot_id: str,
        instance_snapshot_name: str,
        schedule_tag: str,
        retention_days: Optional[int],
    ) -> None:
        """Find and record volume snapshots created from an instance snapshot.

        When an instance snapshot is created, OpenStack automatically creates snapshots
        of all attached volumes. This method finds those volume snapshots by matching
        the snapshot name pattern and records them with a reference to the instance snapshot.

        Args:
            instance_id: ID of the instance
            instance_snapshot_id: ID of the instance snapshot
            instance_snapshot_name: Name of the instance snapshot
            schedule_tag: Schedule tag from the instance
            retention_days: Retention days for the backups
        """
        try:
            # Get volumes attached to the instance
            volumes = await self.openstack_client.get_instance_volumes(instance_id)

            if not volumes:
                self.logger.debug(f"No volumes attached to instance {instance_id}")
                return

            self.logger.debug(
                f"Found {len(volumes)} volumes attached to instance {instance_id}"
            )

            # For each volume, find the snapshot created from this instance snapshot
            for volume in volumes:
                volume_id = volume.get("id")
                if not volume_id:
                    continue

                try:
                    # Get all snapshots for this volume
                    snapshots = await self.openstack_client.list_volume_snapshots()

                    # Filter for snapshots of this volume
                    volume_snapshots = [
                        s for s in snapshots if s.get("volume_id") == volume_id
                    ]

                    if not volume_snapshots:
                        self.logger.debug(f"No snapshots found for volume {volume_id}")
                        continue

                    # Find snapshot by name pattern: "snapshot for <instance_snapshot_name>"
                    # OpenStack automatically names volume snapshots this way
                    expected_snapshot_name = f"snapshot for {instance_snapshot_name}"

                    matching_snapshot = None
                    for snapshot in volume_snapshots:
                        snapshot_name = snapshot.get("name", "")
                        if snapshot_name == expected_snapshot_name:
                            matching_snapshot = snapshot
                            break

                    if not matching_snapshot:
                        self.logger.debug(
                            f"No snapshot found with expected name '{expected_snapshot_name}' for volume {volume_id}"
                        )
                        continue

                    snapshot_id = matching_snapshot.get("id")
                    if not snapshot_id:
                        continue

                    self.logger.info(
                        f"Found related volume snapshot {snapshot_id} (name: {expected_snapshot_name}) "
                        f"for volume {volume_id} from instance snapshot {instance_snapshot_id}"
                    )

                    # Record this volume snapshot with reference to instance snapshot
                    backup_info = BackupInfo(
                        backup_id=snapshot_id,
                        resource_id=volume_id,
                        resource_type="volume",
                        backup_type=BackupType.SNAPSHOT,
                        verified=True,  # Volume snapshots created by instance snapshot are verified
                        schedule_tag=schedule_tag,
                        retention_days=retention_days,
                        related_instance_snapshot_id=instance_snapshot_id,
                    )

                    self.state_manager.record_backup(backup_info)
                    self.logger.debug(
                        f"Recorded volume snapshot {snapshot_id} as related to instance snapshot {instance_snapshot_id}"
                    )

                except Exception as e:
                    self.logger.warning(
                        f"Failed to find/record volume snapshot for volume {volume_id}: {e}"
                    )
                    continue

        except Exception as e:
            self.logger.warning(
                f"Failed to find related volume snapshots for instance {instance_id}: {e}"
            )
