"""Backup operation data models."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class BackupType(Enum):
    """Types of backup operations."""

    SNAPSHOT = "snapshot"
    FULL = "full"
    INCREMENTAL = "incremental"


class OperationStatus(Enum):
    """Status of backup operations."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


@dataclass
class BackupInfo:
    """Information about a completed backup."""

    backup_id: str
    resource_id: str
    resource_type: str  # 'instance' or 'volume'
    backup_type: BackupType
    parent_backup_id: Optional[str] = None
    created_at: Optional[datetime] = None
    verified: bool = False
    schedule_tag: Optional[str] = None
    retention_days: Optional[int] = None  # Retention policy at time of backup creation
    related_instance_snapshot_id: Optional[str] = (
        None  # For volume snapshots created from instance snapshots
    )

    def __post_init__(self):
        """Set created_at if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


@dataclass
class BackupOperation:
    """A backup operation to be executed."""

    resource_id: str
    resource_type: str
    resource_name: str
    operation_type: BackupType
    schedule_tag: str
    parent_backup_id: Optional[str] = None
    priority: int = 0  # Higher number = higher priority
    timeout_minutes: int = 60

    def __post_init__(self):
        """Set priority based on operation type."""
        if self.priority == 0:
            # Snapshots have highest priority, then incrementals, then full backups
            priority_map = {
                BackupType.SNAPSHOT: 100,
                BackupType.INCREMENTAL: 50,
                BackupType.FULL: 10,
            }
            self.priority = priority_map.get(self.operation_type, 0)


@dataclass
class OperationResult:
    """Result of a backup operation."""

    operation: BackupOperation
    status: OperationStatus
    backup_info: Optional[BackupInfo] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate operation duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_successful(self) -> bool:
        """Check if operation was successful."""
        return self.status == OperationStatus.COMPLETED and self.backup_info is not None
