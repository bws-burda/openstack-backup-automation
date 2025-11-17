"""Main execution coordinator for backup operations."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..backup.engine import BackupEngine
from ..backup.models import BackupOperation, BackupType, OperationResult
from ..config.models import Config
from ..core.context import BackupContext
from ..interfaces import (
    NotificationServiceInterface,
    RetentionManagerInterface,
    StateManagerInterface,
    TagScannerInterface,
)
from ..scanner.models import OperationType, ScheduledResource


class ExecutionCoordinator:
    """Coordinates all backup operations including scanning, execution, and cleanup."""

    def __init__(
        self,
        config: Config,
        tag_scanner: TagScannerInterface,
        backup_engine: BackupEngine,
        state_manager: StateManagerInterface,
        retention_manager: RetentionManagerInterface,
        notification_service: NotificationServiceInterface,
    ):
        """Initialize the execution coordinator.

        Args:
            config: System configuration
            tag_scanner: Scanner for discovering scheduled resources
            backup_engine: Engine for executing backup operations
            state_manager: Manager for backup state and history
            retention_manager: Manager for backup cleanup
            notification_service: Service for sending notifications
        """
        self.config = config
        self.tag_scanner = tag_scanner
        self.backup_engine = backup_engine
        self.state_manager = state_manager
        self.retention_manager = retention_manager
        self.notification_service = notification_service
        self.logger = logging.getLogger(__name__)

    async def execute_backup_cycle(
        self, context: BackupContext = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """Execute a complete backup cycle.

        This is the main entry point that orchestrates:
        1. Resource discovery via tag scanning
        2. Backup operation execution
        3. Retention cleanup
        4. Notification of results

        Args:
            context: Backup execution context (test mode, dry run, etc.)
            dry_run: If True, only report what would be done without executing (deprecated, use context)

        Returns:
            Dictionary with execution results and statistics
        """
        # Handle backward compatibility and create context if needed
        if context is None:
            context = BackupContext(dry_run=dry_run)

        cycle_start = datetime.now(timezone.utc)
        self.logger.info(f"Starting backup cycle at {cycle_start}")
        self.logger.info(f"Execution mode: {context.get_mode_description()}")

        if context.should_simulate_operations():
            self.logger.info("DRY RUN MODE - No actual operations will be performed")

        results = {
            "cycle_start": cycle_start,
            "context": context,
            "dry_run": context.should_simulate_operations(),  # For backward compatibility
            "test_mode": context.should_ignore_timing(),
            "discovered_resources": 0,
            "due_resources": 0,
            "operations_executed": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "retention_deleted": 0,
            "errors": [],
            "operation_results": [],
        }

        try:
            # Phase 1: Resource Discovery
            self.logger.info("Phase 1: Discovering scheduled resources")
            discovered_resources = await self._discover_resources()
            results["discovered_resources"] = len(discovered_resources)

            if not discovered_resources:
                self.logger.info("No scheduled resources found")
                return results

            # Phase 2: Determine Due Resources
            self.logger.info("Phase 2: Determining resources due for backup")
            due_resources = await self._get_due_resources(discovered_resources, context)
            results["due_resources"] = len(due_resources)

            if not due_resources:
                self.logger.info("No resources are due for backup at this time")
            else:
                # Phase 3: Execute Backup Operations
                self.logger.info(
                    f"Phase 3: Executing backup operations for {len(due_resources)} resources"
                )
                operation_results = await self._execute_backup_operations(
                    due_resources, context
                )
                results["operation_results"] = operation_results
                results["operations_executed"] = len(operation_results)
                results["successful_operations"] = sum(
                    1 for r in operation_results if r.is_successful
                )
                results["failed_operations"] = sum(
                    1 for r in operation_results if not r.is_successful
                )

            # Phase 4: Retention Cleanup
            self.logger.info("Phase 4: Performing retention cleanup")
            deleted_count = await self._perform_retention_cleanup(context)
            results["retention_deleted"] = deleted_count

            # Phase 5: Send Notifications
            if not context.should_simulate_operations():
                self.logger.info("Phase 5: Sending notifications")
                await self._send_notifications(results)

        except Exception as e:
            error_msg = f"Critical error during backup cycle: {e}"
            self.logger.error(error_msg, exc_info=True)
            results["errors"].append(error_msg)

            # Send error notification
            if not context.should_simulate_operations():
                try:
                    await self._send_error_notification(
                        e, {"phase": "backup_cycle", "results": results}
                    )
                except Exception as notification_error:
                    self.logger.error(
                        f"Failed to send error notification: {notification_error}"
                    )

        finally:
            cycle_end = datetime.now(timezone.utc)
            duration = (cycle_end - cycle_start).total_seconds()
            results["cycle_end"] = cycle_end
            results["duration_seconds"] = duration

            self.logger.info(
                f"Backup cycle completed in {duration:.1f}s: "
                f"{results['successful_operations']}/{results['operations_executed']} operations successful, "
                f"{results['retention_deleted']} backups cleaned up"
            )

        return results

    async def _discover_resources(self) -> List[ScheduledResource]:
        """Discover all scheduled resources via tag scanning."""
        try:
            resources = await self.tag_scanner.scan_all_resources()
            self.logger.info(f"Discovered {len(resources)} scheduled resources")

            # Update resource status in state manager
            for resource in resources:
                try:
                    # Get last backup info from state manager
                    last_backup_info = self.state_manager.get_last_backup(resource.id)
                    if last_backup_info:
                        resource.last_backup = last_backup_info.created_at

                    # Update resource status
                    self.state_manager.update_resource_status(
                        resource.id,
                        resource.last_backup or datetime.now(timezone.utc),
                        active=True,
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to update status for resource {resource.id}: {e}"
                    )

            return resources

        except Exception as e:
            self.logger.error(f"Failed to discover resources: {e}")
            raise

    async def _get_due_resources(
        self, resources: List[ScheduledResource], context: BackupContext
    ) -> List[ScheduledResource]:
        """Determine which resources are due for backup."""
        try:
            if context.should_ignore_timing():
                # In test mode, all resources are considered due
                due_resources = resources
                self.logger.info(
                    f"TEST MODE: All {len(due_resources)} resources marked as due for backup"
                )
            else:
                # Normal mode: check timing constraints
                # First, load last_backup times from database for accurate timing
                for resource in resources:
                    last_backup = self.state_manager.get_last_backup(resource.id)
                    if last_backup:
                        resource.last_backup = last_backup.created_at

                due_resources = self.tag_scanner.get_due_resources(resources)

            if due_resources:
                self.logger.info(
                    f"Found {len(due_resources)} resources due for backup:"
                )
                for resource in due_resources:
                    last_backup_str = (
                        resource.last_backup.strftime("%Y-%m-%d %H:%M:%S")
                        if resource.last_backup
                        else "Never"
                    )
                    mode_indicator = (
                        " (TEST MODE)" if context.should_ignore_timing() else ""
                    )
                    self.logger.info(
                        f"  - {resource.name} ({resource.id}): {resource.schedule_tag}, last backup: {last_backup_str}{mode_indicator}"
                    )

            return due_resources

        except Exception as e:
            self.logger.error(f"Failed to determine due resources: {e}")
            raise

    async def _execute_backup_operations(
        self, resources: List[ScheduledResource], context: BackupContext
    ) -> List[OperationResult]:
        """Execute backup operations for due resources."""
        if not resources:
            return []

        # Convert scheduled resources to backup operations
        operations = []
        for resource in resources:
            try:
                operation = await self._create_backup_operation(resource)
                operations.append(operation)
            except Exception as e:
                self.logger.error(
                    f"Failed to create backup operation for resource {resource.id}: {e}"
                )

        if not operations:
            self.logger.warning("No valid backup operations could be created")
            return []

        if context.should_simulate_operations():
            mode_desc = "DRY RUN" if not context.test_mode else "TEST MODE + DRY RUN"
            self.logger.info(
                f"{mode_desc}: Would execute {len(operations)} backup operations:"
            )
            for op in operations:
                self.logger.info(
                    f"  - {op.resource_name} ({op.resource_id}): {op.operation_type.value}"
                )

            # Create simulated results for proper counting
            from datetime import datetime, timezone

            from ..backup.models import OperationResult, OperationStatus

            simulated_results = []
            for op in operations:
                # Create simulated backup info
                from ..backup.models import BackupInfo

                simulated_backup_info = BackupInfo(
                    backup_id=f"dry-run-{op.resource_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                    resource_id=op.resource_id,
                    resource_type=op.resource_type,
                    backup_type=op.operation_type,
                    parent_backup_id=op.parent_backup_id,
                    verified=True,  # Assume success in dry run
                    schedule_tag=op.schedule_tag,
                )

                result = OperationResult(
                    operation=op,
                    status=OperationStatus.COMPLETED,
                    backup_info=simulated_backup_info,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
                simulated_results.append(result)

            return simulated_results

        # Execute operations in parallel
        try:
            results = await self.backup_engine.execute_parallel_operations(operations)

            # Log results
            successful = [r for r in results if r.is_successful]
            failed = [r for r in results if not r.is_successful]

            self.logger.info(
                f"Backup operations completed: {len(successful)} successful, {len(failed)} failed"
            )

            for result in failed:
                self.logger.error(
                    f"Backup failed for {result.operation.resource_name} ({result.operation.resource_id}): "
                    f"{result.error_message}"
                )

            return results

        except Exception as e:
            self.logger.error(f"Failed to execute backup operations: {e}")
            raise

    async def _create_backup_operation(
        self, resource: ScheduledResource
    ) -> BackupOperation:
        """Create a backup operation from a scheduled resource."""
        # Determine backup type based on operation type and resource type
        if resource.schedule_info.operation_type == OperationType.SNAPSHOT:
            # SNAPSHOT tags always create snapshots
            backup_type = BackupType.SNAPSHOT
            parent_backup_id = None
        elif resource.schedule_info.operation_type == OperationType.BACKUP:
            # BACKUP tags only create volume backups
            if resource.type.value == "volume":
                # Use backup strategy to determine type (full or incremental)
                backup_type = self.backup_engine.determine_backup_type(resource.id)
                parent_backup_id = None
                if backup_type == BackupType.INCREMENTAL:
                    parent_backup_id = self.backup_engine.get_parent_backup_id(
                        resource.id, backup_type
                    )
                    if not parent_backup_id:
                        # No valid parent, create full backup instead
                        backup_type = BackupType.FULL
            else:
                # Instance with BACKUP tag: This should not happen as we only create
                # volume operations for BACKUP tags on instances
                raise ValueError(
                    f"BACKUP tag on instance {resource.id} should only create volume operations, not instance operations"
                )
        else:
            raise ValueError(
                f"Unknown operation type: {resource.schedule_info.operation_type}"
            )

        return BackupOperation(
            resource_id=resource.id,
            resource_type=resource.type.value,
            resource_name=resource.name,
            operation_type=backup_type,
            schedule_tag=resource.schedule_tag,
            parent_backup_id=parent_backup_id,
            timeout_minutes=self.config.backup.operation_timeout_minutes,
        )

    async def _perform_retention_cleanup(self, context: BackupContext) -> int:
        """Perform retention cleanup of old backups."""
        try:
            if context.should_simulate_operations():
                mode_desc = (
                    "DRY RUN" if not context.test_mode else "TEST MODE + DRY RUN"
                )
                self.logger.info(f"{mode_desc}: Simulating retention cleanup")

                # Still run retention check in dry-run to show what would be deleted
                cleanup_result = await self.retention_manager.cleanup_expired_backups(
                    self.config.retention_policies,
                    use_tag_policies=True,
                    use_batch_deletion=True,
                    batch_size=5,
                    backup_config=self.config.backup,
                    dry_run=True,  # Pass dry_run flag to retention manager
                )

                deleted_count = cleanup_result.get("deleted_count", 0)
                if deleted_count > 0:
                    self.logger.info(
                        f"{mode_desc}: Would delete {deleted_count} backups"
                    )
                else:
                    self.logger.info(f"{mode_desc}: No backups would be deleted")
                return 0

            cleanup_result = await self.retention_manager.cleanup_expired_backups(
                self.config.retention_policies,
                use_tag_policies=True,
                use_batch_deletion=True,
                batch_size=5,
                backup_config=self.config.backup,
            )

            deleted_count = cleanup_result.get("deleted_count", 0)

            if deleted_count > 0:
                self.logger.info(
                    f"Retention cleanup completed: {deleted_count} backups deleted"
                )
            else:
                self.logger.info(
                    "Retention cleanup completed: no backups needed deletion"
                )

            return deleted_count

        except Exception as e:
            self.logger.error(f"Failed to perform retention cleanup: {e}")
            return 0

    async def _send_notifications(self, results: Dict[str, Any]) -> None:
        """Send notifications about backup cycle results."""
        try:
            # Send backup report if there were operations
            if results["operations_executed"] > 0:
                successful_ops = [
                    r for r in results["operation_results"] if r.is_successful
                ]
                failed_ops = [
                    r for r in results["operation_results"] if not r.is_successful
                ]

                success = self.notification_service.send_backup_report(
                    successful_ops, failed_ops
                )
                if not success:
                    self.logger.warning("Failed to send backup report notification")

            # Send retention report if there was cleanup
            if results["retention_deleted"] > 0:
                success = self.notification_service.send_retention_report(
                    results["retention_deleted"], results["errors"]
                )
                if not success:
                    self.logger.warning("Failed to send retention report notification")

        except Exception as e:
            self.logger.error(f"Failed to send notifications: {e}")

    async def _send_error_notification(
        self, error: Exception, context: Dict[str, Any]
    ) -> None:
        """Send error notification."""
        try:
            success = self.notification_service.send_error_notification(error, context)
            if not success:
                self.logger.warning("Failed to send error notification")
        except Exception as e:
            self.logger.error(f"Failed to send error notification: {e}")

    async def get_system_status(self) -> Dict[str, Any]:
        """Get current system status and statistics."""
        try:
            # Get resource counts
            all_resources = await self.tag_scanner.scan_all_resources()

            # Load last_backup times from database for accurate due calculation
            for resource in all_resources:
                last_backup = self.state_manager.get_last_backup(resource.id)
                if last_backup:
                    resource.last_backup = last_backup.created_at

            # For status display, use normal timing logic (respects actual backup times)
            due_resources = self.tag_scanner.get_due_resources(all_resources)

            # Get recent backup statistics
            recent_backups = []
            for resource in all_resources:
                last_backup = self.state_manager.get_last_backup(resource.id)
                if last_backup:
                    recent_backups.append(last_backup)

            # Sort by creation time, most recent first
            recent_backups.sort(
                key=lambda b: b.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )

            # Check system health
            health_check = await self.validate_system_health()
            is_healthy = health_check["overall_status"] == "healthy"

            status = {
                "timestamp": datetime.now(timezone.utc),
                "healthy": is_healthy,
                "total_scheduled_resources": len(all_resources),
                "resources_due_for_backup": len(due_resources),
                "recent_backups_count": len(recent_backups),
                "last_backup_time": (
                    recent_backups[0].created_at if recent_backups else None
                ),
                "config": {
                    "max_concurrent_operations": self.config.backup.max_concurrent_operations,
                    "operation_timeout_minutes": self.config.backup.operation_timeout_minutes,
                    "full_backup_interval_days": self.config.backup.full_backup_interval_days,
                    "scheduling_mode": self.config.scheduling.mode.value,
                    "check_interval_minutes": self.config.scheduling.check_interval_minutes,
                },
                "resources_by_type": {
                    "instances": len(
                        [r for r in all_resources if r.type.value == "instance"]
                    ),
                    "volumes": len(
                        [r for r in all_resources if r.type.value == "volume"]
                    ),
                },
                "resources_by_operation": {
                    "snapshot": len(
                        [
                            r
                            for r in all_resources
                            if r.schedule_info.operation_type == OperationType.SNAPSHOT
                        ]
                    ),
                    "backup": len(
                        [
                            r
                            for r in all_resources
                            if r.schedule_info.operation_type == OperationType.BACKUP
                        ]
                    ),
                },
            }

            return status

        except Exception as e:
            self.logger.error(f"Failed to get system status: {e}")
            return {
                "timestamp": datetime.now(timezone.utc),
                "error": str(e),
            }

    async def validate_system_health(self) -> Dict[str, Any]:
        """Validate system health and configuration."""
        health = {
            "timestamp": datetime.now(timezone.utc),
            "overall_status": "healthy",
            "checks": {},
            "warnings": [],
            "errors": [],
        }

        try:
            # Check OpenStack connectivity
            try:
                # Try to scan resources as a connectivity test
                resources = await self.tag_scanner.scan_all_resources()
                health["checks"]["openstack_connectivity"] = "ok"
                health["checks"][
                    "resource_discovery"
                ] = f"ok - {len(resources)} resources found"
            except Exception as e:
                health["checks"]["openstack_connectivity"] = f"failed - {e}"
                health["errors"].append(f"OpenStack connectivity failed: {e}")
                health["overall_status"] = "unhealthy"

            # Check database connectivity
            try:
                # Try to get backup count as a database test
                _ = self.state_manager.get_last_backup("test-resource-id")
                health["checks"]["database_connectivity"] = "ok"
            except Exception as e:
                health["checks"]["database_connectivity"] = f"failed - {e}"
                health["errors"].append(f"Database connectivity failed: {e}")
                health["overall_status"] = "unhealthy"

            # Check configuration validity
            try:
                # Basic configuration validation
                if not self.config.openstack.auth_url:
                    health["warnings"].append("OpenStack auth_url not configured")
                if not self.config.notifications.recipient:
                    health["warnings"].append("Email recipient not configured")
                health["checks"]["configuration"] = "ok"
            except Exception as e:
                health["checks"]["configuration"] = f"failed - {e}"
                health["errors"].append(f"Configuration validation failed: {e}")
                health["overall_status"] = "unhealthy"

            # Set overall status based on errors
            if health["errors"]:
                health["overall_status"] = "unhealthy"
            elif health["warnings"]:
                health["overall_status"] = "degraded"

        except Exception as e:
            health["overall_status"] = "unhealthy"
            health["errors"].append(f"Health check failed: {e}")

        return health
