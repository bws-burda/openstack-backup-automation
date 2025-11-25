"""Tag scanner implementation."""

import logging
import re
from datetime import datetime, time, timezone
from typing import TYPE_CHECKING, Any, List, Optional

from .models import (
    Frequency,
    OperationType,
    ResourceType,
    ScheduledResource,
    ScheduleInfo,
)

if TYPE_CHECKING:
    pass


class TagScanner:
    """Scans OpenStack resources for schedule tags and manages resource discovery."""

    # Tag format: {TYPE}-{FREQUENCY}-{TIME}[-RETAIN{DAYS}][-FULL{DAYS}]
    TAG_PATTERN = re.compile(
        r"^(SNAPSHOT|BACKUP)-(DAILY|WEEKLY|MONTHLY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)-(\d{4})(?:-RETAIN(\d+))?(?:-FULL(\d+))?$"
    )

    def __init__(
        self, openstack_client: Any, timezone: str = "UTC"
    ):  # OpenStackClientInterface
        self.openstack_client = openstack_client
        self.timezone = timezone
        self.logger = logging.getLogger(__name__)

    async def scan_instances(self) -> List[ScheduledResource]:
        """Scan Nova instances for schedule tags."""
        scheduled_resources = []

        # Get all instances with tags
        self.logger.info("Scanning Nova instances for schedule tags")
        try:
            instances = await self.openstack_client.get_instances_with_tags()
        except Exception as e:
            self.logger.error(f"Failed to retrieve instances from OpenStack: {e}")
            return []

        for instance in instances:
            instance_id = instance.get("id")
            if not instance_id:
                self.logger.warning("Found instance without ID, skipping")
                continue

            instance_name = instance.get("name", f"instance-{instance_id}")
            tags = instance.get("tags", [])

            # Look for schedule tags
            valid_schedule_tags = []
            for tag in tags:
                schedule_info = self.parse_schedule_tag(tag)
                if schedule_info:
                    valid_schedule_tags.append((tag, schedule_info))

            if valid_schedule_tags:
                # Use the first valid schedule tag
                tag, schedule_info = valid_schedule_tags[0]
                if len(valid_schedule_tags) > 1:
                    self.logger.warning(
                        f"Instance {instance_id} has multiple schedule tags, using first valid one: {tag}"
                    )

                # Add the instance itself
                # Handle different operation types
                if schedule_info.operation_type == OperationType.SNAPSHOT:
                    # SNAPSHOT tags: Create instance snapshot operation
                    scheduled_resource = ScheduledResource(
                        id=instance_id,
                        type=ResourceType.INSTANCE,
                        name=instance_name,
                        schedule_info=schedule_info,
                        last_scanned=datetime.now(timezone.utc),
                    )
                    scheduled_resources.append(scheduled_resource)
                    self.logger.debug(
                        f"Found scheduled instance for snapshot: {instance_name} ({instance_id}) with schedule {tag}"
                    )
                elif schedule_info.operation_type == OperationType.BACKUP:
                    # BACKUP tags: Only backup attached volumes, no instance snapshot
                    self.logger.debug(
                        f"Found instance with BACKUP tag: {instance_name} ({instance_id}) - will backup attached volumes only"
                    )
                    try:
                        attached_volumes = (
                            await self.openstack_client.get_instance_volumes(
                                instance_id
                            )
                        )
                        for volume in attached_volumes:
                            volume_id = volume.get("id")
                            volume_name = volume.get("name", f"volume-{volume_id}")

                            if volume_id:
                                # Create a volume backup schedule with the same timing as the instance
                                volume_scheduled_resource = ScheduledResource(
                                    id=volume_id,
                                    type=ResourceType.VOLUME,
                                    name=f"{volume_name} (auto-from-{instance_name})",
                                    schedule_info=schedule_info,  # Same schedule as the instance
                                    last_scanned=datetime.now(timezone.utc),
                                )
                                scheduled_resources.append(volume_scheduled_resource)
                                self.logger.info(
                                    f"Auto-scheduled volume backup: {volume_name} ({volume_id}) from instance {instance_name}"
                                )

                    except Exception as e:
                        self.logger.warning(
                            f"Could not get attached volumes for instance {instance_id}: {e}"
                        )
                        # Continue - BACKUP tag on instance requires volume access

        self.logger.info(f"Found {len(scheduled_resources)} scheduled instances")
        return scheduled_resources

    async def scan_volumes(self) -> List[ScheduledResource]:
        """Scan Cinder volumes for schedule tags."""
        scheduled_resources = []

        # Get all volumes with tags
        self.logger.info("Scanning Cinder volumes for schedule tags")
        try:
            volumes = await self.openstack_client.get_volumes_with_tags()
        except Exception as e:
            self.logger.error(f"Failed to retrieve volumes from OpenStack: {e}")
            return []

        for volume in volumes:
            volume_id = volume.get("id")
            if not volume_id:
                self.logger.warning("Found volume without ID, skipping")
                continue

            volume_name = volume.get("name", f"volume-{volume_id}")

            # Volume tags might be in metadata or tags field
            tags = volume.get("tags", [])
            if not tags and "metadata" in volume:
                # Some OpenStack versions store tags in metadata
                metadata = volume["metadata"]

                # Only accept "backup" as metadata key for simplicity
                if "backup" in metadata and self._looks_like_schedule_tag(
                    metadata["backup"]
                ):
                    tags.append(metadata["backup"])

                # Fallback: check metadata keys and values as before
                tags.extend(
                    [
                        f"{k}:{v}"
                        for k, v in metadata.items()
                        if self._looks_like_schedule_tag(k)
                        or self._looks_like_schedule_tag(v)
                    ]
                )
                tags.extend(
                    [k for k in metadata.keys() if self._looks_like_schedule_tag(k)]
                )

            # Look for schedule tags
            valid_schedule_tags = []
            for tag in tags:
                schedule_info = self.parse_schedule_tag(tag)
                if schedule_info:
                    valid_schedule_tags.append((tag, schedule_info))

            if valid_schedule_tags:
                # Use the first valid schedule tag
                tag, schedule_info = valid_schedule_tags[0]
                if len(valid_schedule_tags) > 1:
                    self.logger.warning(
                        f"Volume {volume_id} has multiple schedule tags, using first valid one: {tag}"
                    )

                scheduled_resource = ScheduledResource(
                    id=volume_id,
                    type=ResourceType.VOLUME,
                    name=volume_name,
                    schedule_info=schedule_info,
                    last_scanned=datetime.now(timezone.utc),
                )
                scheduled_resources.append(scheduled_resource)
                self.logger.debug(
                    f"Found scheduled volume: {volume_name} ({volume_id}) with schedule {tag}"
                )

        self.logger.info(f"Found {len(scheduled_resources)} scheduled volumes")
        return scheduled_resources

    def parse_schedule_tag(self, tag: str) -> Optional[ScheduleInfo]:
        """Parse a schedule tag string into ScheduleInfo."""
        if not tag:
            return None

        # Handle tags that might have colons (from metadata)
        tag_parts = tag.split(":")
        tag_to_parse = tag_parts[0] if len(tag_parts) > 1 else tag

        match = self.TAG_PATTERN.match(tag_to_parse.upper())
        if not match:
            # Check if it looks like a schedule tag but has invalid format
            if any(
                prefix in tag_to_parse.upper() for prefix in ["SNAPSHOT-", "BACKUP-"]
            ):
                self.logger.warning(
                    f"Invalid schedule tag format ignored: '{tag}'. Expected format: {{TYPE}}-{{FREQUENCY}}-{{TIME}}"
                )
            return None

        try:
            operation_type = OperationType(match.group(1))
            frequency = Frequency(match.group(2))
            time_str = match.group(3)
            retain_days_str = match.group(4)  # RETAIN suffix
            full_days_str = match.group(5)  # FULL suffix

            # Validate time format (HHMM)
            try:
                hour = int(time_str[:2])
                minute = int(time_str[2:])
                if not (0 <= hour <= 23) or not (0 <= minute <= 59):
                    self.logger.warning(
                        f"Invalid time in schedule tag '{tag}': {time_str}. Time must be in HHMM format (00:00-23:59)"
                    )
                    return None
            except (ValueError, IndexError):
                self.logger.warning(
                    f"Invalid time format in schedule tag '{tag}': {time_str}. Expected HHMM format"
                )
                return None

            # Parse optional retention days
            retention_days = None
            if retain_days_str:
                try:
                    retention_days = int(retain_days_str)
                    if retention_days <= 0:
                        self.logger.warning(
                            f"Invalid retention days in schedule tag '{tag}': {retain_days_str}. Must be positive"
                        )
                        return None
                except ValueError:
                    self.logger.warning(
                        f"Invalid retention days format in schedule tag '{tag}': {retain_days_str}"
                    )
                    return None

            # Parse optional full backup interval days
            full_backup_interval_days = None
            if full_days_str:
                try:
                    full_backup_interval_days = int(full_days_str)
                    if full_backup_interval_days <= 0:
                        self.logger.warning(
                            f"Invalid full backup interval in schedule tag '{tag}': {full_days_str}. Must be positive"
                        )
                        return None
                except ValueError:
                    self.logger.warning(
                        f"Invalid full backup interval format in schedule tag '{tag}': {full_days_str}"
                    )
                    return None

            return ScheduleInfo(
                operation_type=operation_type,
                frequency=frequency,
                time=time_str,
                retention_days=retention_days,
                full_backup_interval_days=full_backup_interval_days,
            )
        except (ValueError, KeyError) as e:
            self.logger.warning(f"Invalid schedule tag values in '{tag}': {e}")
            return None

    def is_backup_due(self, resource: ScheduledResource) -> bool:
        """Check if a backup is due for the given resource.

        Implements defensive backup strategy:
        - If no previous backup exists, create one immediately (defensive backup)
        - Otherwise, follow the regular schedule

        Times in schedule tags are interpreted in the configured timezone.
        """
        import pytz

        # Get current time in configured timezone
        tz = pytz.timezone(self.timezone)
        now = datetime.now(tz)
        schedule_info = resource.schedule_info

        # DEFENSIVE BACKUP STRATEGY: If no backup exists, create one immediately
        if resource.last_backup is None:
            self.logger.info(
                f"Defensive backup triggered for {resource.name} ({resource.id}) - no previous backup found"
            )
            return True

        # Parse the scheduled time
        try:
            hour = int(schedule_info.time[:2])
            minute = int(schedule_info.time[2:])
            scheduled_time = time(hour, minute)
        except (ValueError, IndexError):
            self.logger.warning(
                f"Invalid time format in schedule for resource {resource.id}: {schedule_info.time}"
            )
            return False

        # Check frequency-specific conditions
        if schedule_info.frequency == Frequency.DAILY:
            # Daily backups are due every day after the scheduled time
            current_time = now.time()

            # Check if we already did a backup today
            last_backup_date = resource.last_backup.date()
            today = now.date()

            # If we already did a backup today, we're not due
            if last_backup_date == today:
                return False

            # If we haven't done a backup today and we're past the scheduled time
            if last_backup_date < today and current_time >= scheduled_time:
                return True

            return False

        elif schedule_info.frequency == Frequency.WEEKLY:
            # Weekly backups - check if at least 7 days have passed
            days_since_last = (now - resource.last_backup).days
            if days_since_last >= 7:
                # Also check if we're past the scheduled time today
                current_time = now.time()
                return current_time >= scheduled_time
            return False

        elif schedule_info.frequency == Frequency.MONTHLY:
            # Monthly backups - check if at least 28 days have passed
            days_since_last = (now - resource.last_backup).days
            if days_since_last >= 28:
                # Also check if we're past the scheduled time today
                current_time = now.time()
                return current_time >= scheduled_time
            return False

        else:
            # Weekday-specific backups (MONDAY, TUESDAY, etc.)
            weekday_map = {
                Frequency.MONDAY: 0,
                Frequency.TUESDAY: 1,
                Frequency.WEDNESDAY: 2,
                Frequency.THURSDAY: 3,
                Frequency.FRIDAY: 4,
                Frequency.SATURDAY: 5,
                Frequency.SUNDAY: 6,
            }

            target_weekday = weekday_map.get(schedule_info.frequency)
            if target_weekday is None:
                return False

            # Check if today is the target weekday
            if now.weekday() != target_weekday:
                return False

            # Check if we're past the scheduled time
            current_time = now.time()
            if current_time < scheduled_time:
                return False

            # If it's the right weekday and we're past the scheduled time, we're due
            # (regardless of whether a backup was already done today)
            return True

        return False

    async def scan_all_resources(self) -> List[ScheduledResource]:
        """Scan both instances and volumes for schedule tags."""
        self.logger.info("Starting comprehensive resource scan")

        # Scan instances and volumes concurrently
        import asyncio

        instance_task = self.scan_instances()
        volume_task = self.scan_volumes()

        try:
            instances, volumes = await asyncio.gather(instance_task, volume_task)
            all_resources = instances + volumes

            self.logger.info(
                f"Resource scan complete: {len(instances)} instances, {len(volumes)} volumes, {len(all_resources)} total scheduled resources"
            )
            return all_resources

        except Exception as e:
            self.logger.error(f"Error during resource scan: {e}")
            # Try to get partial results
            try:
                instances = await instance_task
                self.logger.warning(
                    "Volume scan failed, returning only instance results"
                )
                return instances
            except Exception:
                try:
                    volumes = await volume_task
                    self.logger.warning(
                        "Instance scan failed, returning only volume results"
                    )
                    return volumes
                except Exception:
                    self.logger.error("Both instance and volume scans failed")
                    return []

    def get_resources_by_schedule_type(
        self, resources: List[ScheduledResource], operation_type: OperationType
    ) -> List[ScheduledResource]:
        """Filter resources by operation type (SNAPSHOT or BACKUP)."""
        return [
            r for r in resources if r.schedule_info.operation_type == operation_type
        ]

    def get_resources_by_frequency(
        self, resources: List[ScheduledResource], frequency: Frequency
    ) -> List[ScheduledResource]:
        """Filter resources by schedule frequency."""
        return [r for r in resources if r.schedule_info.frequency == frequency]

    def get_due_resources(
        self, resources: List[ScheduledResource]
    ) -> List[ScheduledResource]:
        """Get all resources that are due for backup."""
        due_resources = []
        for resource in resources:
            try:
                if self.is_backup_due(resource):
                    due_resources.append(resource)
            except Exception as e:
                self.logger.warning(
                    f"Error checking if backup is due for resource {resource.id}: {e}"
                )

        self.logger.info(
            f"Found {len(due_resources)} resources due for backup out of {len(resources)} total"
        )
        return due_resources

    def _looks_like_schedule_tag(self, tag: str) -> bool:
        """Quick check if a string looks like a schedule tag."""
        return bool(self.TAG_PATTERN.match(tag.upper()))
