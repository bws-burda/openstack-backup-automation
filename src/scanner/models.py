"""Scanner data models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class OperationType(Enum):
    """Backup operation types."""

    SNAPSHOT = "SNAPSHOT"
    BACKUP = "BACKUP"


class Frequency(Enum):
    """Schedule frequency types."""

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


class ResourceType(Enum):
    """OpenStack resource types."""

    INSTANCE = "instance"
    VOLUME = "volume"


@dataclass
class ScheduleInfo:
    """Parsed schedule information from tags."""

    operation_type: OperationType
    frequency: Frequency
    time: str  # HHMM format
    retention_days: Optional[int] = None  # Override from RETAIN suffix
    full_backup_interval_days: Optional[int] = None  # Override from FULL suffix

    def __post_init__(self):
        """Validate time format."""
        if not isinstance(self.time, str) or len(self.time) != 4:
            raise ValueError(f"Time must be in HHMM format, got: {self.time}")

        try:
            hour = int(self.time[:2])
            minute = int(self.time[2:])
            if not (0 <= hour <= 23) or not (0 <= minute <= 59):
                raise ValueError(f"Invalid time: {self.time}")
        except ValueError as e:
            raise ValueError(f"Invalid time format: {self.time}") from e


@dataclass
class ScheduledResource:
    """A resource scheduled for backup operations."""

    id: str
    type: ResourceType
    name: str
    schedule_info: ScheduleInfo
    last_backup: Optional[datetime] = None
    last_scanned: Optional[datetime] = None
    active: bool = True

    @property
    def schedule_tag(self) -> str:
        """Generate the schedule tag string."""
        base_tag = f"{self.schedule_info.operation_type.value}-{self.schedule_info.frequency.value}-{self.schedule_info.time}"

        # Add RETAIN suffix if specified
        if self.schedule_info.retention_days is not None:
            base_tag += f"-RETAIN{self.schedule_info.retention_days}"

        # Add FULL suffix if specified
        if self.schedule_info.full_backup_interval_days is not None:
            base_tag += f"-FULL{self.schedule_info.full_backup_interval_days}"

        return base_tag
