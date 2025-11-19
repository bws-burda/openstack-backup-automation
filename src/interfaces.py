"""Abstract base classes and interfaces for core components."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from .backup.models import BackupInfo, BackupOperation, OperationResult
from .config.models import Config, EmailSettings, OpenStackCredentials, RetentionPolicy
from .scanner.models import ScheduledResource, ScheduleInfo


class ConfigurationManagerInterface(ABC):
    """Interface for configuration management."""

    @abstractmethod
    def load_config(self, config_path: str) -> Config:
        """Load configuration from file."""
        pass

    @abstractmethod
    def get_openstack_credentials(self) -> OpenStackCredentials:
        """Get OpenStack authentication credentials."""
        pass

    @abstractmethod
    def get_email_settings(self) -> EmailSettings:
        """Get email notification settings."""
        pass

    @abstractmethod
    def get_retention_policies(self) -> Dict[str, RetentionPolicy]:
        """Get retention policies configuration."""
        pass

    @abstractmethod
    def validate_config(self, config: Config) -> bool:
        """Validate configuration completeness and correctness."""
        pass


class TagScannerInterface(ABC):
    """Interface for tag scanning and resource discovery."""

    @abstractmethod
    async def scan_instances(self) -> List[ScheduledResource]:
        """Scan Nova instances for schedule tags."""
        pass

    @abstractmethod
    async def scan_volumes(self) -> List[ScheduledResource]:
        """Scan Cinder volumes for schedule tags."""
        pass

    @abstractmethod
    async def scan_all_resources(self) -> List[ScheduledResource]:
        """Scan both instances and volumes for schedule tags."""
        pass

    @abstractmethod
    def parse_schedule_tag(self, tag: str) -> Optional[ScheduleInfo]:
        """Parse a schedule tag string into ScheduleInfo."""
        pass

    @abstractmethod
    def is_backup_due(self, resource: ScheduledResource) -> bool:
        """Check if a backup is due for the given resource."""
        pass

    @abstractmethod
    def get_resources_by_schedule_type(
        self, resources: List[ScheduledResource], operation_type: Any
    ) -> List[ScheduledResource]:
        """Filter resources by operation type (SNAPSHOT or BACKUP)."""
        pass

    @abstractmethod
    def get_resources_by_frequency(
        self, resources: List[ScheduledResource], frequency: Any
    ) -> List[ScheduledResource]:
        """Filter resources by schedule frequency."""
        pass

    @abstractmethod
    def get_due_resources(
        self, resources: List[ScheduledResource]
    ) -> List[ScheduledResource]:
        """Get all resources that are due for backup."""
        pass


class BackupEngineInterface(ABC):
    """Interface for backup and snapshot operations."""

    @abstractmethod
    async def create_instance_snapshot(self, instance_id: str, name: str) -> str:
        """Create a snapshot of an instance."""
        pass

    @abstractmethod
    async def create_volume_snapshot(self, volume_id: str, name: str) -> str:
        """Create a snapshot of a volume."""
        pass

    @abstractmethod
    async def create_volume_backup(
        self,
        volume_id: str,
        name: str,
        backup_type: str,
        parent_backup_id: Optional[str] = None,
    ) -> str:
        """Create a backup of a volume."""
        pass

    @abstractmethod
    async def verify_backup_success(self, backup_id: str, resource_type: str) -> bool:
        """Verify that a backup was created successfully."""
        pass

    @abstractmethod
    async def execute_parallel_operations(
        self, operations: List[BackupOperation]
    ) -> List[OperationResult]:
        """Execute multiple backup operations in parallel."""
        pass


class StateManagerInterface(ABC):
    """Interface for state management and backup history."""

    @abstractmethod
    def record_backup(self, backup_info: BackupInfo) -> None:
        """Record a completed backup in the database."""
        pass

    @abstractmethod
    def get_last_backup(self, resource_id: str) -> Optional[BackupInfo]:
        """Get the most recent backup for a resource."""
        pass

    @abstractmethod
    def get_backup_chain(self, resource_id: str) -> List[BackupInfo]:
        """Get the complete backup chain for a resource."""
        pass

    @abstractmethod
    def get_backups_older_than(self, days: int) -> List[BackupInfo]:
        """Get backups older than specified number of days."""
        pass

    @abstractmethod
    def get_all_backups(self) -> List[BackupInfo]:
        """Get all backups in the database."""
        pass

    @abstractmethod
    def delete_backup_record(self, backup_id: str) -> None:
        """Delete a backup record from the database."""
        pass

    @abstractmethod
    def update_resource_status(
        self, resource_id: str, last_backup: datetime, active: bool = True
    ) -> None:
        """Update resource status and last backup time."""
        pass

    @abstractmethod
    def get_last_full_backup(self, resource_id: str) -> Optional[BackupInfo]:
        """Get the most recent full backup for a resource."""
        pass

    @abstractmethod
    def get_dependent_incrementals(self, full_backup_id: str) -> List[BackupInfo]:
        """Get all incremental backups that depend on a full backup."""
        pass

    @abstractmethod
    def get_backup_by_id(self, backup_id: str) -> Optional[BackupInfo]:
        """Get backup information by backup ID."""
        pass


class RetentionManagerInterface(ABC):
    """Interface for backup retention and cleanup."""

    @abstractmethod
    def get_backups_to_delete(
        self, retention_policy: RetentionPolicy
    ) -> List[BackupInfo]:
        """Get list of backups that should be deleted based on retention policy."""
        pass

    @abstractmethod
    async def delete_backup(self, backup_info: BackupInfo) -> bool:
        """Delete a backup from OpenStack and update database."""
        pass

    @abstractmethod
    def can_delete_full_backup(self, backup_info: BackupInfo) -> bool:
        """Check if a full backup can be safely deleted (no dependent incrementals)."""
        pass

    @abstractmethod
    async def cleanup_expired_backups(
        self, retention_policies: Dict[str, RetentionPolicy]
    ) -> int:
        """Clean up expired backups and return count of deleted backups."""
        pass


class NotificationServiceInterface(ABC):
    """Interface for notifications and error reporting."""

    @abstractmethod
    def send_error_notification(
        self, error: Exception, context: Dict[str, Any]
    ) -> bool:
        """Send error notification email."""
        pass

    @abstractmethod
    def send_backup_report(
        self,
        successful_operations: List[OperationResult],
        failed_operations: List[OperationResult],
    ) -> bool:
        """Send backup operation summary report."""
        pass

    @abstractmethod
    def send_retention_report(self, deleted_count: int, errors: List[str]) -> bool:
        """Send retention cleanup report."""
        pass


class OpenStackClientInterface(ABC):
    """Interface for OpenStack API operations."""

    @abstractmethod
    def authenticate(self, credentials: OpenStackCredentials) -> bool:
        """Authenticate with OpenStack."""
        pass

    @abstractmethod
    async def get_instances_with_tags(
        self, tag_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get instances with optional tag filtering."""
        pass

    @abstractmethod
    async def get_volumes_with_tags(
        self, tag_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get volumes with optional tag filtering."""
        pass

    @abstractmethod
    async def get_instance_volumes(self, instance_id: str) -> List[Dict[str, Any]]:
        """Get all volumes attached to a specific instance."""
        pass

    @abstractmethod
    async def create_instance_snapshot(self, instance_id: str, name: str) -> str:
        """Create instance snapshot via Nova API."""
        pass

    @abstractmethod
    async def create_volume_snapshot(self, volume_id: str, name: str) -> str:
        """Create volume snapshot via Cinder API."""
        pass

    @abstractmethod
    async def create_volume_backup(
        self,
        volume_id: str,
        name: str,
        incremental: bool = False,
        parent_id: Optional[str] = None,
    ) -> str:
        """Create volume backup via Cinder API."""
        pass

    @abstractmethod
    async def delete_snapshot(self, snapshot_id: str, resource_type: str) -> bool:
        """Delete a snapshot."""
        pass

    @abstractmethod
    async def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup."""
        pass

    @abstractmethod
    async def get_backup_status(
        self, backup_id: str, resource_type: str
    ) -> Optional[str]:
        """Get the status of a backup or snapshot."""
        pass


class HealthCheckerInterface(ABC):
    """Interface for system health checking."""

    @abstractmethod
    async def check_system_health(self):
        """Perform comprehensive system health check."""
        pass

    @abstractmethod
    async def check_component_health(self, component_name: str):
        """Check health of a specific component."""
        pass


class StatusReporterInterface(ABC):
    """Interface for status reporting."""

    @abstractmethod
    def generate_health_report(self, system_status) -> Dict[str, Any]:
        """Generate a comprehensive health report."""
        pass

    @abstractmethod
    def generate_backup_summary(self, days: int = 7) -> Optional[Dict[str, Any]]:
        """Generate backup operation summary."""
        pass

    @abstractmethod
    def send_health_alert(self, system_status) -> bool:
        """Send health alert if system has critical issues."""
        pass

    @abstractmethod
    def send_status_report(
        self, system_status, include_backup_summary: bool = True
    ) -> bool:
        """Send comprehensive status report."""
        pass
