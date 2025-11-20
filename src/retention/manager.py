"""Retention manager implementation."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytz

from ..backup.models import BackupInfo, BackupType
from ..config.models import RetentionPolicy
from ..interfaces import (
    OpenStackClientInterface,
    RetentionManagerInterface,
    StateManagerInterface,
)


class RetentionManager(RetentionManagerInterface):
    """Manages backup retention and cleanup operations."""

    def __init__(
        self,
        state_manager: StateManagerInterface,
        openstack_client: OpenStackClientInterface,
        timezone_str: str = "UTC",
    ):
        self.state_manager = state_manager
        self.openstack_client = openstack_client
        self.logger = logging.getLogger(__name__)

        # Set timezone from config
        try:
            self.tz = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            self.logger.warning(
                f"Unknown timezone '{timezone_str}', falling back to UTC"
            )
            self.tz = pytz.UTC

    def _get_min_datetime(self) -> datetime:
        """Get a timezone-aware minimum datetime."""
        return datetime.min.replace(tzinfo=self.tz)

    def _get_now(self) -> datetime:
        """Get current time in configured timezone."""
        return datetime.now(self.tz)

    def get_backups_to_delete(
        self, retention_policy: RetentionPolicy
    ) -> List[BackupInfo]:
        """Get list of backups that should be deleted based on retention policy.

        Args:
            retention_policy: Retention policy to apply

        Returns:
            List of backups that can be safely deleted
        """
        self.logger.info(
            f"Evaluating backups for deletion with {retention_policy.retention_days} day retention"
        )

        # Get all backups older than retention period
        old_backups = self.state_manager.get_backups_older_than(
            retention_policy.retention_days
        )

        if not old_backups:
            self.logger.info("No backups older than retention period found")
            return []

        self.logger.info(
            f"Found {len(old_backups)} backups older than {retention_policy.retention_days} days"
        )

        # Group backups by resource
        backups_by_resource = {}
        for backup in old_backups:
            resource_id = backup.resource_id
            if resource_id not in backups_by_resource:
                backups_by_resource[resource_id] = []
            backups_by_resource[resource_id].append(backup)

        backups_to_delete = []

        for resource_id, resource_backups in backups_by_resource.items():
            self.logger.debug(
                f"Processing {len(resource_backups)} old backups for resource {resource_id}"
            )

            # Get all backups for this resource (including newer ones)
            all_resource_backups = self.state_manager.get_backup_chain(resource_id)

            # Sort by creation date
            all_resource_backups.sort(
                key=lambda b: b.created_at or self._get_min_datetime()
            )
            resource_backups.sort(
                key=lambda b: b.created_at or self._get_min_datetime()
            )

            # Apply retention policy rules
            deletable_backups = self._apply_retention_rules(
                resource_backups, all_resource_backups, retention_policy
            )

            self.logger.debug(
                f"Resource {resource_id}: {len(deletable_backups)} backups marked for deletion"
            )
            backups_to_delete.extend(deletable_backups)

        self.logger.info(f"Total backups marked for deletion: {len(backups_to_delete)}")
        return backups_to_delete

    def _apply_retention_rules(
        self,
        old_backups: List[BackupInfo],
        all_backups: List[BackupInfo],
        policy: RetentionPolicy,
    ) -> List[BackupInfo]:
        """Apply retention policy rules to determine which backups can be deleted.

        Args:
            old_backups: Backups older than retention period
            all_backups: All backups for the resource
            policy: Retention policy to apply

        Returns:
            List of backups that can be safely deleted
        """
        deletable = []
        resource_id = old_backups[0].resource_id if old_backups else "unknown"

        # Count total backups
        total_backups = len(all_backups)

        self.logger.debug(
            f"Applying retention rules for resource {resource_id}: "
            f"{len(old_backups)} old backups, {total_backups} total backups"
        )

        for backup in old_backups:
            can_delete = True
            skip_reason = None

            # Rule 1: Always keep at least 1 backup
            remaining_after_deletion = total_backups - len(deletable) - 1
            if remaining_after_deletion < 1:
                can_delete = False
                skip_reason = (
                    f"Would leave only {remaining_after_deletion} backups (minimum: 1)"
                )

            # Rule 2: Check if it's the last full backup and policy says to keep it
            elif policy.keep_last_full_backup and backup.backup_type == BackupType.FULL:
                if self._is_last_full_backup(backup, all_backups):
                    can_delete = False
                    skip_reason = "Last full backup (protected by policy)"

            # Rule 3: For full backups, check if there are dependent incrementals
            elif backup.backup_type == BackupType.FULL:
                if not self.can_delete_full_backup(backup):
                    can_delete = False
                    skip_reason = "Has dependent incremental backups"

            # Rule 4: For incremental backups, check if parent still exists
            elif backup.backup_type == BackupType.INCREMENTAL:
                if backup.parent_backup_id:
                    parent_exists = any(
                        b.backup_id == backup.parent_backup_id for b in all_backups
                    )
                    if not parent_exists:
                        # Parent is gone, this incremental is orphaned and can be deleted
                        self.logger.debug(
                            f"Incremental backup {backup.backup_id} is orphaned (parent missing)"
                        )

            if can_delete:
                deletable.append(backup)
                self.logger.debug(
                    f"Backup {backup.backup_id} ({backup.backup_type.value}) marked for deletion"
                )
            else:
                self.logger.debug(
                    f"Backup {backup.backup_id} ({backup.backup_type.value}) protected: {skip_reason}"
                )

        return deletable

    def _is_last_full_backup(
        self, backup: BackupInfo, all_backups: List[BackupInfo]
    ) -> bool:
        """Check if this is the most recent full backup for the resource."""
        full_backups = [b for b in all_backups if b.backup_type == BackupType.FULL]
        if not full_backups:
            return False

        # Sort by creation date and check if this is the latest
        # Use datetime.min with UTC timezone to avoid comparison errors
        min_datetime = datetime.min.replace(tzinfo=timezone.utc)
        full_backups.sort(key=lambda b: b.created_at or min_datetime, reverse=True)
        return full_backups[0].backup_id == backup.backup_id

    async def delete_backup(self, backup_info: BackupInfo) -> bool:
        """Delete a backup from OpenStack and update database.

        Args:
            backup_info: Information about the backup to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            self.logger.info(
                f"Deleting backup {backup_info.backup_id} ({backup_info.backup_type.value}) "
                f"for resource {backup_info.resource_id}"
            )

            # Delete from OpenStack
            if backup_info.backup_type == BackupType.SNAPSHOT:
                success = await self.openstack_client.delete_snapshot(
                    backup_info.backup_id, backup_info.resource_type
                )
            else:
                success = await self.openstack_client.delete_backup(
                    backup_info.backup_id
                )

            if success:
                self.logger.info(f"Successfully deleted backup {backup_info.backup_id}")

                # If this is an instance snapshot, also delete related volume snapshots
                if (
                    backup_info.backup_type == BackupType.SNAPSHOT
                    and backup_info.resource_type == "instance"
                ):
                    await self._delete_related_volume_snapshots(backup_info.backup_id)

                # Remove from database AFTER all related deletions are done
                self.state_manager.delete_backup_record(backup_info.backup_id)
                return True
            else:
                self.logger.error(
                    f"Failed to delete backup {backup_info.backup_id} from OpenStack"
                )
                return False

        except Exception as e:
            self.logger.error(
                f"Exception while deleting backup {backup_info.backup_id}: {e}"
            )
            return False

    def can_delete_full_backup(self, backup_info: BackupInfo) -> bool:
        """Check if a full backup can be safely deleted (no dependent incrementals)."""
        if backup_info.backup_type != BackupType.FULL:
            return True

        # Check for dependent incremental backups
        dependent_incrementals = self.state_manager.get_dependent_incrementals(
            backup_info.backup_id
        )
        return len(dependent_incrementals) == 0

    async def cleanup_expired_backups(
        self,
        retention_policies: Dict[str, RetentionPolicy],
        use_tag_policies: bool = True,
        use_batch_deletion: bool = True,
        batch_size: int = 5,
        backup_config=None,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """Clean up expired backups with enhanced tag-based policies and batch deletion.

        Args:
            retention_policies: Dictionary of retention policies
            use_tag_policies: If True, use tag-embedded retention policies
            use_batch_deletion: If True, use batch deletion for better performance
            batch_size: Number of backups to delete in parallel per batch
            dry_run: If True, only simulate deletion and log what would be deleted

        Returns:
            Dictionary with detailed cleanup results
        """
        cleanup_result = {
            "use_tag_policies": use_tag_policies,
            "use_batch_deletion": use_batch_deletion,
            "batch_size": batch_size,
            "deleted_count": 0,
            "failed_count": 0,
            "space_freed_bytes": 0,
            "policies_applied": (
                list(retention_policies.keys()) if retention_policies else ["default"]
            ),
            "batch_results": None,
            "chain_deletions": [],
        }

        # Use default policy if no specific policies defined
        if not retention_policies:
            retention_policies = {"default": RetentionPolicy(retention_days=30)}

        default_policy = retention_policies.get(
            "default", next(iter(retention_policies.values()))
        )

        # Get backups to delete using appropriate method
        if use_tag_policies:
            self.logger.info("Using tag-based retention policies for cleanup")
            backups_to_delete = self.get_backups_to_delete_with_tag_policies(
                default_policy, retention_policies, backup_config
            )
        else:
            self.logger.info("Using single retention policy for cleanup")
            backups_to_delete = self.get_backups_to_delete(default_policy)

        if not backups_to_delete:
            self.logger.info("No backups eligible for deletion")
            return cleanup_result

        # Log what would be deleted (useful for dry-run)
        self.logger.info(
            f"Found {len(backups_to_delete)} backups eligible for deletion"
        )
        for backup in backups_to_delete:
            self.logger.info(
                f"  - {backup.backup_id} ({backup.backup_type.value}): "
                f"resource {backup.resource_id}, created {backup.created_at}"
            )

        # If dry-run, stop here
        if dry_run:
            cleanup_result["deleted_count"] = len(backups_to_delete)
            self.logger.info(f"DRY RUN: Would delete {len(backups_to_delete)} backups")
            return cleanup_result

        # Sort by creation date (oldest first) to maintain backup chain integrity
        backups_to_delete.sort(key=lambda b: b.created_at or self._get_min_datetime())

        # Separate instance snapshots from volume snapshots
        # Delete instance snapshots first, then volume snapshots (to avoid FK constraints)
        instance_snapshots = [
            b
            for b in backups_to_delete
            if b.backup_type == BackupType.SNAPSHOT and b.resource_type == "instance"
        ]
        volume_snapshots = [
            b
            for b in backups_to_delete
            if b.backup_type == BackupType.SNAPSHOT and b.resource_type == "volume"
        ]
        other_backups = [
            b for b in backups_to_delete if b.backup_type != BackupType.SNAPSHOT
        ]

        # Process in order: instance snapshots first, then volume snapshots, then other backups
        backups_to_delete = instance_snapshots + volume_snapshots + other_backups

        # Handle full backups with dependents first
        full_backups_with_dependents = []
        standalone_backups = []

        for backup in backups_to_delete:
            if backup.backup_type == BackupType.FULL:
                dependent_incrementals = self.state_manager.get_dependent_incrementals(
                    backup.backup_id
                )
                if dependent_incrementals:
                    # This full backup has dependents - handle specially
                    full_backups_with_dependents.append(
                        (backup, dependent_incrementals)
                    )
                else:
                    standalone_backups.append(backup)
            else:
                standalone_backups.append(backup)

        # Process full backups with dependents (delete dependents first)
        for full_backup, dependents in full_backups_with_dependents:
            try:
                chain_result = {
                    "full_backup_id": full_backup.backup_id,
                    "dependents_deleted": 0,
                    "full_backup_deleted": False,
                    "errors": [],
                }

                # Delete dependent incrementals first
                if use_batch_deletion and len(dependents) > 1:
                    # Use batch deletion for dependents
                    batch_result = await self.delete_backups_batch(
                        dependents, batch_size
                    )
                    chain_result["dependents_deleted"] = len(
                        batch_result["successful_deletions"]
                    )
                    cleanup_result["deleted_count"] += chain_result[
                        "dependents_deleted"
                    ]
                    cleanup_result["failed_count"] += len(
                        batch_result["failed_deletions"]
                    )
                    cleanup_result["space_freed_bytes"] += batch_result[
                        "space_freed_bytes"
                    ]

                    if batch_result["failed_deletions"]:
                        chain_result["errors"].extend(
                            [f["error"] for f in batch_result["failed_deletions"]]
                        )
                else:
                    # Delete dependents sequentially
                    for incremental in dependents:
                        if await self.delete_backup(incremental):
                            chain_result["dependents_deleted"] += 1
                            cleanup_result["deleted_count"] += 1
                            cleanup_result["space_freed_bytes"] += (
                                incremental.size_bytes or 0
                            )
                        else:
                            cleanup_result["failed_count"] += 1
                            chain_result["errors"].append(
                                f"Failed to delete dependent {incremental.backup_id}"
                            )

                # Now delete the full backup itself
                if await self.delete_backup(full_backup):
                    chain_result["full_backup_deleted"] = True
                    cleanup_result["deleted_count"] += 1
                    cleanup_result["space_freed_bytes"] += full_backup.size_bytes or 0
                else:
                    cleanup_result["failed_count"] += 1
                    chain_result["errors"].append(
                        f"Failed to delete full backup {full_backup.backup_id}"
                    )

                cleanup_result["chain_deletions"].append(chain_result)

            except Exception as e:
                self.logger.error(
                    f"Exception while processing full backup chain {full_backup.backup_id}: {e}"
                )
                cleanup_result["failed_count"] += 1 + len(dependents)
                cleanup_result["chain_deletions"].append(
                    {
                        "full_backup_id": full_backup.backup_id,
                        "dependents_deleted": 0,
                        "full_backup_deleted": False,
                        "errors": [f"Exception: {str(e)}"],
                    }
                )

        # Process standalone backups
        if standalone_backups:
            if use_batch_deletion:
                self.logger.info(
                    f"Using batch deletion for {len(standalone_backups)} standalone backups"
                )
                batch_result = await self.delete_backups_batch(
                    standalone_backups, batch_size
                )
                cleanup_result["batch_results"] = batch_result
                cleanup_result["deleted_count"] += len(
                    batch_result["successful_deletions"]
                )
                cleanup_result["failed_count"] += len(batch_result["failed_deletions"])
                cleanup_result["space_freed_bytes"] += batch_result["space_freed_bytes"]
            else:
                self.logger.info(
                    f"Using sequential deletion for {len(standalone_backups)} standalone backups"
                )
                for backup in standalone_backups:
                    try:
                        if await self.delete_backup(backup):
                            cleanup_result["deleted_count"] += 1
                            cleanup_result["space_freed_bytes"] += (
                                backup.size_bytes or 0
                            )
                        else:
                            cleanup_result["failed_count"] += 1
                    except Exception as e:
                        self.logger.error(
                            f"Exception while deleting backup {backup.backup_id}: {e}"
                        )
                        cleanup_result["failed_count"] += 1

        self.logger.info(
            f"Cleanup completed: {cleanup_result['deleted_count']} deleted, "
            f"{cleanup_result['failed_count']} failed, "
            f"{cleanup_result['space_freed_bytes']} bytes freed"
        )

        return cleanup_result

    def calculate_backup_age(self, backup_info: BackupInfo) -> int:
        """Calculate the age of a backup in days.

        Args:
            backup_info: Backup information

        Returns:
            Age in days
        """
        if not backup_info.created_at:
            return 0

        now = self._get_now()
        # Ensure both datetimes are timezone-aware in configured timezone
        backup_time = backup_info.created_at
        if backup_time.tzinfo is None:
            # Assume naive datetimes are in the configured timezone
            backup_time = self.tz.localize(backup_time)
        else:
            # Convert aware datetimes to configured timezone
            backup_time = backup_time.astimezone(self.tz)

        age = now - backup_time
        return age.days

    def get_retention_candidates(
        self,
        retention_policies: Dict[str, RetentionPolicy],
        resource_filter: Optional[str] = None,
    ) -> Dict[str, List[BackupInfo]]:
        """Get all backup retention candidates grouped by policy.

        Args:
            retention_policies: Dictionary of retention policies
            resource_filter: Optional resource ID filter

        Returns:
            Dictionary mapping policy names to lists of deletable backups
        """
        candidates = {}

        # Get all backups grouped by their schedule_tag
        all_backups = self.state_manager.get_all_backups()
        backups_by_tag = {}

        for backup in all_backups:
            if backup.schedule_tag:
                if backup.schedule_tag not in backups_by_tag:
                    backups_by_tag[backup.schedule_tag] = []
                backups_by_tag[backup.schedule_tag].append(backup)

        # Apply retention policies based on schedule tags
        for policy_name, policy in retention_policies.items():
            self.logger.debug(f"Evaluating retention policy '{policy_name}'")
            policy_candidates = []

            # Apply policy to backups from each schedule tag separately
            for schedule_tag, tag_backups in backups_by_tag.items():
                # Extract retention days from the schedule tag (e.g., RETAIN14)
                tag_retention_days = self._extract_retention_from_tag(schedule_tag)

                if tag_retention_days is not None:
                    # Use tag-specific retention
                    tag_candidates = self._get_backups_to_delete_with_retention(
                        tag_backups, tag_retention_days
                    )
                else:
                    # Fall back to backup-type-specific retention
                    tag_candidates = []
                    for backup in tag_backups:
                        # Get retention based on backup type from retention policies
                        type_retention_days = self.get_retention_days_for_backup_type(
                            backup.backup_type, retention_policies
                        )

                        if self.calculate_backup_age(backup) > type_retention_days:
                            tag_candidates.append(backup)

                policy_candidates.extend(tag_candidates)

            # Apply resource filter if specified
            if resource_filter:
                policy_candidates = [
                    backup
                    for backup in policy_candidates
                    if backup.resource_id == resource_filter
                ]

            candidates[policy_name] = policy_candidates
            self.logger.debug(
                f"Policy '{policy_name}': {len(policy_candidates)} candidates"
            )

        return candidates

    def validate_deletion_safety(self, backup_info: BackupInfo) -> Dict[str, any]:
        """Validate if a backup can be safely deleted without breaking chains.

        Args:
            backup_info: Backup to validate for deletion

        Returns:
            Dictionary with safety validation results
        """
        safety_result = {
            "safe": True,
            "warnings": [],
            "errors": [],
            "dependent_backups": [],
            "chain_impact": None,
        }

        # Check for dependent incremental backups
        if backup_info.backup_type == BackupType.FULL:
            dependents = self.state_manager.get_dependent_incrementals(
                backup_info.backup_id
            )
            if dependents:
                safety_result["safe"] = False
                safety_result["errors"].append(
                    f"Full backup has {len(dependents)} dependent incremental backups"
                )
                safety_result["dependent_backups"] = [d.backup_id for d in dependents]

        # Check if this is the last full backup for the resource
        if backup_info.backup_type == BackupType.FULL:
            all_backups = self.state_manager.get_backup_chain(backup_info.resource_id)
            full_backups = [b for b in all_backups if b.backup_type == BackupType.FULL]

            if (
                len(full_backups) == 1
                and full_backups[0].backup_id == backup_info.backup_id
            ):
                safety_result["warnings"].append(
                    "This is the last full backup for the resource"
                )
                safety_result["chain_impact"] = "last_full_backup"

        # Check if backup is verified
        if not backup_info.verified:
            safety_result["warnings"].append("Backup is not verified")

        return safety_result

    def get_backup_chain_summary(self, resource_id: str) -> Dict[str, any]:
        """Get a summary of backup chains for a resource.

        Args:
            resource_id: ID of the resource

        Returns:
            Dictionary with chain summary information
        """
        all_backups = self.state_manager.get_backup_chain(resource_id)

        if not all_backups:
            return {
                "resource_id": resource_id,
                "total_backups": 0,
                "full_backups": 0,
                "incremental_backups": 0,
                "snapshots": 0,
                "oldest_backup": None,
                "newest_backup": None,
                "total_size_bytes": 0,
                "verified_backups": 0,
                "chains": [],
            }

        # Sort by creation date
        all_backups.sort(key=lambda b: b.created_at or self._get_min_datetime())

        # Calculate statistics
        full_backups = [b for b in all_backups if b.backup_type == BackupType.FULL]
        incremental_backups = [
            b for b in all_backups if b.backup_type == BackupType.INCREMENTAL
        ]
        snapshots = [b for b in all_backups if b.backup_type == BackupType.SNAPSHOT]

        total_size = sum(b.size_bytes or 0 for b in all_backups)
        verified_count = sum(1 for b in all_backups if b.verified)

        # Analyze chains
        chains = []
        for full_backup in full_backups:
            dependents = self.state_manager.get_dependent_incrementals(
                full_backup.backup_id
            )
            chain_info = {
                "root_backup_id": full_backup.backup_id,
                "root_created_at": full_backup.created_at,
                "incremental_count": len(dependents),
                "chain_size_bytes": (full_backup.size_bytes or 0)
                + sum(d.size_bytes or 0 for d in dependents),
                "all_verified": full_backup.verified
                and all(d.verified for d in dependents),
            }
            chains.append(chain_info)

        return {
            "resource_id": resource_id,
            "total_backups": len(all_backups),
            "full_backups": len(full_backups),
            "incremental_backups": len(incremental_backups),
            "snapshots": len(snapshots),
            "oldest_backup": all_backups[0].created_at if all_backups else None,
            "newest_backup": all_backups[-1].created_at if all_backups else None,
            "total_size_bytes": total_size,
            "verified_backups": verified_count,
            "chains": chains,
        }

    def schedule_cleanup_operation(
        self, retention_policies: Dict[str, RetentionPolicy], dry_run: bool = True
    ) -> Dict[str, any]:
        """Schedule a cleanup operation and return execution plan.

        Args:
            retention_policies: Dictionary of retention policies to apply
            dry_run: If True, only plan the operation without executing

        Returns:
            Dictionary with cleanup operation plan
        """
        operation_plan = {
            "dry_run": dry_run,
            "timestamp": self._get_now(),
            "policies_applied": list(retention_policies.keys()),
            "total_candidates": 0,
            "safe_deletions": [],
            "unsafe_deletions": [],
            "warnings": [],
            "estimated_space_freed": 0,
        }

        # Get all retention candidates
        candidates_by_policy = self.get_retention_candidates(retention_policies)

        # Flatten all candidates and remove duplicates
        all_candidates = []
        seen_backup_ids = set()

        for policy_name, candidates in candidates_by_policy.items():
            for candidate in candidates:
                if candidate.backup_id not in seen_backup_ids:
                    all_candidates.append(candidate)
                    seen_backup_ids.add(candidate.backup_id)

        operation_plan["total_candidates"] = len(all_candidates)

        # Validate each candidate for safe deletion
        for candidate in all_candidates:
            safety_check = self.validate_deletion_safety(candidate)

            deletion_info = {
                "backup_id": candidate.backup_id,
                "resource_id": candidate.resource_id,
                "backup_type": candidate.backup_type.value,
                "created_at": candidate.created_at,
                "age_days": self.calculate_backup_age(candidate),
                "size_bytes": candidate.size_bytes or 0,
                "safety_check": safety_check,
            }

            if safety_check["safe"]:
                operation_plan["safe_deletions"].append(deletion_info)
                operation_plan["estimated_space_freed"] += deletion_info["size_bytes"]
            else:
                operation_plan["unsafe_deletions"].append(deletion_info)

            # Collect warnings
            operation_plan["warnings"].extend(safety_check.get("warnings", []))

        self.logger.info(
            f"Cleanup operation planned: {len(operation_plan['safe_deletions'])} safe deletions, "
            f"{len(operation_plan['unsafe_deletions'])} unsafe deletions"
        )

        return operation_plan

    async def delete_backups_batch(
        self, backups: List[BackupInfo], batch_size: int = 5
    ) -> Dict[str, any]:
        """Delete multiple backups in parallel batches for better performance.

        Args:
            backups: List of backups to delete
            batch_size: Number of backups to delete in parallel per batch

        Returns:
            Dictionary with batch deletion results
        """
        batch_result = {
            "total_backups": len(backups),
            "batch_size": batch_size,
            "successful_deletions": [],
            "failed_deletions": [],
            "total_batches": 0,
            "space_freed_bytes": 0,
        }

        if not backups:
            return batch_result

        # Group backups into batches
        batches = [
            backups[i : i + batch_size] for i in range(0, len(backups), batch_size)
        ]
        batch_result["total_batches"] = len(batches)

        self.logger.info(
            f"Starting batch deletion of {len(backups)} backups in {len(batches)} batches"
        )

        for batch_idx, batch in enumerate(batches):
            self.logger.debug(
                f"Processing batch {batch_idx + 1}/{len(batches)} with {len(batch)} backups"
            )

            # Create deletion tasks for this batch
            tasks = []
            for backup in batch:
                task = self._delete_backup_with_result(backup)
                tasks.append(task)

            # Execute batch in parallel
            try:
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for backup, result in zip(batch, batch_results):
                    if isinstance(result, Exception):
                        batch_result["failed_deletions"].append(
                            {
                                "backup_id": backup.backup_id,
                                "backup_type": backup.backup_type.value,
                                "resource_id": backup.resource_id,
                                "error": str(result),
                            }
                        )
                        self.logger.error(
                            f"Batch deletion failed for {backup.backup_id}: {result}"
                        )
                    elif result:
                        batch_result["successful_deletions"].append(
                            {
                                "backup_id": backup.backup_id,
                                "backup_type": backup.backup_type.value,
                                "resource_id": backup.resource_id,
                                "size_bytes": backup.size_bytes or 0,
                            }
                        )
                        batch_result["space_freed_bytes"] += backup.size_bytes or 0
                        self.logger.debug(
                            f"Successfully deleted backup {backup.backup_id}"
                        )
                    else:
                        batch_result["failed_deletions"].append(
                            {
                                "backup_id": backup.backup_id,
                                "backup_type": backup.backup_type.value,
                                "resource_id": backup.resource_id,
                                "error": "deletion_returned_false",
                            }
                        )
                        self.logger.error(
                            f"Batch deletion returned False for {backup.backup_id}"
                        )

            except Exception as e:
                self.logger.error(
                    f"Exception during batch {batch_idx + 1} execution: {e}"
                )
                # Mark all backups in this batch as failed
                for backup in batch:
                    batch_result["failed_deletions"].append(
                        {
                            "backup_id": backup.backup_id,
                            "backup_type": backup.backup_type.value,
                            "resource_id": backup.resource_id,
                            "error": f"batch_exception: {str(e)}",
                        }
                    )

        success_count = len(batch_result["successful_deletions"])
        failed_count = len(batch_result["failed_deletions"])

        self.logger.info(
            f"Batch deletion completed: {success_count} successful, {failed_count} failed, "
            f"{batch_result['space_freed_bytes']} bytes freed"
        )

        return batch_result

    def extract_retention_from_tag(self, schedule_tag: str) -> Optional[Dict[str, any]]:
        """Extract retention and full backup interval from schedule tag.

        Tag formats supported:
        - BACKUP-DAILY-0300-RETAIN30  (30 days retention)
        - BACKUP-DAILY-0300-RETAIN30-FULL7  (30 days retention, new full backup every 7 days)
        - SNAPSHOT-WEEKLY-1200-RETAIN7  (7 days retention)
        - BACKUP-MONTHLY-0100-RETAIN90-FULL14  (90 days retention, new full backup every 14 days)

        Args:
            schedule_tag: Schedule tag string

        Returns:
            Dictionary with retention_days and full_backup_interval_days, or None if no retention info found
        """
        if not schedule_tag:
            return None

        parts = schedule_tag.upper().split("-")
        retention_info = {}

        for part in parts:
            # Extract retention days
            if part.startswith("RETAIN") and len(part) > 6:
                try:
                    retention_days = int(part[6:])  # Remove 'RETAIN' prefix
                    retention_info["retention_days"] = retention_days
                except ValueError:
                    continue

            # Extract full backup interval
            elif part.startswith("FULL") and len(part) > 4:
                try:
                    full_interval = int(part[4:])  # Remove 'FULL' prefix
                    retention_info["full_backup_interval_days"] = full_interval
                except ValueError:
                    continue

        return retention_info if retention_info else None

    def extract_full_backup_interval_from_tag(self, schedule_tag: str) -> Optional[int]:
        """Extract full backup interval from schedule tag.

        Args:
            schedule_tag: Schedule tag string

        Returns:
            Number of days between full backups, or None if not specified
        """
        retention_info = self.extract_retention_from_tag(schedule_tag)
        if retention_info:
            return retention_info.get("full_backup_interval_days")
        return None

    def should_create_new_full_backup(
        self, resource_id: str, schedule_tag: str, default_full_backup_interval: int = 7
    ) -> bool:
        """Check if a new full backup should be created based on tag configuration.

        Args:
            resource_id: ID of the resource
            schedule_tag: Schedule tag with potential FULL{n} parameter
            default_full_backup_interval: Default interval in days if not specified in tag

        Returns:
            True if a new full backup should be created
        """
        # Get the full backup interval from tag or use default
        full_backup_interval = self.extract_full_backup_interval_from_tag(schedule_tag)
        if full_backup_interval is None:
            full_backup_interval = default_full_backup_interval

        # Get the last full backup for this resource
        last_full_backup = self.state_manager.get_last_full_backup(resource_id)

        if not last_full_backup:
            # No full backup exists, should create one
            return True

        # Check if enough time has passed since the last full backup
        if not last_full_backup.created_at:
            # No creation date, assume we need a new one
            return True

        now = self._get_now()
        days_since_last_full = (now - last_full_backup.created_at).days

        should_create = days_since_last_full >= full_backup_interval

        if should_create:
            self.logger.info(
                f"Resource {resource_id}: {days_since_last_full} days since last full backup "
                f"(interval: {full_backup_interval} days) - new full backup needed"
            )
        else:
            self.logger.debug(
                f"Resource {resource_id}: {days_since_last_full} days since last full backup "
                f"(interval: {full_backup_interval} days) - incremental backup sufficient"
            )

        return should_create

    def get_backup_strategy_for_resource(
        self, resource_id: str, schedule_tag: str, default_full_backup_interval: int = 7
    ) -> Dict[str, any]:
        """Get the backup strategy (full vs incremental) for a resource based on its tag.

        Args:
            resource_id: ID of the resource
            schedule_tag: Schedule tag with potential FULL{n} parameter
            default_full_backup_interval: Default interval in days if not specified in tag

        Returns:
            Dictionary with backup strategy information
        """
        strategy = {
            "resource_id": resource_id,
            "schedule_tag": schedule_tag,
            "should_create_full_backup": False,
            "backup_type_recommended": BackupType.INCREMENTAL,
            "full_backup_interval_days": default_full_backup_interval,
            "days_since_last_full": None,
            "last_full_backup_id": None,
            "reasoning": "",
        }

        # Extract full backup interval from tag
        tag_interval = self.extract_full_backup_interval_from_tag(schedule_tag)
        if tag_interval:
            strategy["full_backup_interval_days"] = tag_interval

        # Get last full backup info
        last_full_backup = self.state_manager.get_last_full_backup(resource_id)

        if not last_full_backup:
            strategy["should_create_full_backup"] = True
            strategy["backup_type_recommended"] = BackupType.FULL
            strategy["reasoning"] = "No previous full backup found"
            return strategy

        strategy["last_full_backup_id"] = last_full_backup.backup_id

        if last_full_backup.created_at:
            now = self._get_now()
            days_since_last_full = (now - last_full_backup.created_at).days
            strategy["days_since_last_full"] = days_since_last_full

            if days_since_last_full >= strategy["full_backup_interval_days"]:
                strategy["should_create_full_backup"] = True
                strategy["backup_type_recommended"] = BackupType.FULL
                strategy["reasoning"] = (
                    f"Last full backup is {days_since_last_full} days old (interval: {strategy['full_backup_interval_days']} days)"
                )
            else:
                strategy["reasoning"] = (
                    f"Last full backup is {days_since_last_full} days old (interval: {strategy['full_backup_interval_days']} days) - incremental sufficient"
                )
        else:
            strategy["should_create_full_backup"] = True
            strategy["backup_type_recommended"] = BackupType.FULL
            strategy["reasoning"] = "Last full backup has no creation date"

        return strategy

    def create_retention_policy_from_tag(
        self, schedule_tag: str, default_policy: RetentionPolicy
    ) -> RetentionPolicy:
        """Create a retention policy from tag information with fallback to defaults.

        Args:
            schedule_tag: Schedule tag string
            default_policy: Default policy to use as fallback

        Returns:
            RetentionPolicy with tag-specific retention days and full backup interval
        """
        tag_retention_info = self.extract_retention_from_tag(schedule_tag)

        if not tag_retention_info:
            return default_policy

        # Create new policy with tag values, falling back to defaults
        return RetentionPolicy(
            retention_days=tag_retention_info.get(
                "retention_days", default_policy.retention_days
            ),
            keep_last_full_backup=default_policy.keep_last_full_backup,
        )

    def get_backups_to_delete_with_tag_policies(
        self,
        default_retention_policy: RetentionPolicy,
        global_retention_policies: Optional[Dict[str, RetentionPolicy]] = None,
        backup_config=None,
    ) -> List[BackupInfo]:
        """Get backups to delete using tag-based retention policies.

        Args:
            default_retention_policy: Default policy for backups without tag retention info
            global_retention_policies: Optional global policies that can override tag policies

        Returns:
            List of backups that can be safely deleted
        """
        self.logger.info(
            "Evaluating backups for deletion using tag-based retention policies"
        )

        # Get all backups (we'll filter by age per-policy)
        # Use a large window to get all potentially old backups, then filter individually
        max_retention_days = 365  # Get all backups from last year

        # Handle case where default_retention_policy is None
        if default_retention_policy is None:
            default_retention_policy = RetentionPolicy(retention_days=30)

        if global_retention_policies:
            # Handle case where values might be dicts or RetentionPolicy objects
            policy_retention_days = []
            for policy in global_retention_policies.values():
                if hasattr(policy, "retention_days"):
                    policy_retention_days.append(policy.retention_days)
                elif isinstance(policy, dict) and "retention_days" in policy:
                    policy_retention_days.append(policy["retention_days"])

            if policy_retention_days:
                max_retention_days = max(max_retention_days, max(policy_retention_days))

        # No need to consider backup_config retention settings anymore
        # as we use retention_policies exclusively

        # Get ALL backups (not just old ones) - we'll filter per-resource based on their specific retention
        all_old_backups = self.state_manager.get_all_backups()

        if not all_old_backups:
            self.logger.info("No old backups found")
            return []

        # Group backups by resource
        backups_by_resource = {}
        for backup in all_old_backups:
            resource_id = backup.resource_id
            if resource_id not in backups_by_resource:
                backups_by_resource[resource_id] = []
            backups_by_resource[resource_id].append(backup)

        backups_to_delete = []

        for resource_id, resource_backups in backups_by_resource.items():
            self.logger.debug(
                f"Processing {len(resource_backups)} backups for resource {resource_id}"
            )

            # Get all backups for this resource (including newer ones)
            all_resource_backups = self.state_manager.get_backup_chain(resource_id)

            # Sort by creation date
            all_resource_backups.sort(
                key=lambda b: b.created_at or self._get_min_datetime()
            )
            resource_backups.sort(
                key=lambda b: b.created_at or self._get_min_datetime()
            )

            # Process each backup with its specific retention policy
            for backup in resource_backups:
                # Use retention_days stored with the backup (from creation time)
                # If not set, fall back to effective policy
                if backup.retention_days is not None:
                    retention_days = backup.retention_days
                    self.logger.debug(
                        f"Using stored retention for backup {backup.backup_id}: {retention_days} days"
                    )
                else:
                    # Fallback to effective policy if retention_days not stored
                    effective_policy = self._get_effective_retention_policy(
                        backup, default_retention_policy, global_retention_policies
                    )
                    retention_days = effective_policy.retention_days
                    self.logger.debug(
                        f"Using effective retention for backup {backup.backup_id}: {retention_days} days"
                    )

                # Check if backup is old enough for deletion
                backup_age = self.calculate_backup_age(backup)
                if backup_age < retention_days:
                    continue  # Not old enough for deletion

                # Apply retention rules
                effective_policy = RetentionPolicy(retention_days=retention_days)
                if self._is_backup_deletable_under_policy(
                    backup, all_resource_backups, effective_policy
                ):
                    backups_to_delete.append(backup)
                    self.logger.debug(
                        f"Backup {backup.backup_id} marked for deletion "
                        f"(retention: {retention_days}d)"
                    )

                    # If this is a volume snapshot with a related instance snapshot,
                    # also mark the instance snapshot for deletion to avoid FK constraints
                    if (
                        backup.backup_type == BackupType.SNAPSHOT
                        and backup.resource_type == "volume"
                        and backup.related_instance_snapshot_id
                    ):
                        related_instance_snapshot = self.state_manager.get_backup_by_id(
                            backup.related_instance_snapshot_id
                        )
                        if (
                            related_instance_snapshot
                            and related_instance_snapshot not in backups_to_delete
                        ):
                            backups_to_delete.append(related_instance_snapshot)
                            self.logger.debug(
                                f"Also marking related instance snapshot {related_instance_snapshot.backup_id} "
                                f"for deletion (FK constraint)"
                            )

        self.logger.info(
            f"Total backups marked for deletion with tag policies: {len(backups_to_delete)}"
        )
        return backups_to_delete

    def _get_effective_retention_policy(
        self,
        backup: BackupInfo,
        default_policy: RetentionPolicy,
        global_policies: Optional[Dict[str, RetentionPolicy]] = None,
    ) -> RetentionPolicy:
        """Get the effective retention policy for a specific backup.

        Priority order:
        1. Tag-embedded retention info (highest priority)
        2. Global policy matching (by backup type, resource type, etc.)
        3. Default policy (fallback)

        Args:
            backup: Backup to get policy for
            default_policy: Default retention policy
            global_policies: Optional global policies

        Returns:
            Effective retention policy for this backup
        """
        # 1. Check for tag-embedded retention info (highest priority)
        if backup.schedule_tag:
            tag_retention_info = self.extract_retention_from_tag(backup.schedule_tag)
            if tag_retention_info:
                # Create policy with tag retention
                return RetentionPolicy(
                    retention_days=tag_retention_info.get(
                        "retention_days", default_policy.retention_days
                    ),
                    keep_last_full_backup=default_policy.keep_last_full_backup,
                )

        # 2. Check global policies (medium priority)
        if global_policies:
            # Match by backup type
            if (
                backup.backup_type == BackupType.SNAPSHOT
                and "snapshots" in global_policies
            ):
                return global_policies["snapshots"]
            elif (
                backup.backup_type == BackupType.FULL
                and "full_backups" in global_policies
            ):
                return global_policies["full_backups"]
            elif (
                backup.backup_type == BackupType.INCREMENTAL
                and "incremental_backups" in global_policies
            ):
                return global_policies["incremental_backups"]

            # Match by resource type
            if backup.resource_type == "instance" and "instances" in global_policies:
                return global_policies["instances"]
            elif backup.resource_type == "volume" and "volumes" in global_policies:
                return global_policies["volumes"]

            # Match by schedule frequency (from tag)
            if backup.schedule_tag:
                if "DAILY" in backup.schedule_tag and "daily" in global_policies:
                    return global_policies["daily"]
                elif "WEEKLY" in backup.schedule_tag and "weekly" in global_policies:
                    return global_policies["weekly"]
                elif "MONTHLY" in backup.schedule_tag and "monthly" in global_policies:
                    return global_policies["monthly"]

        # 3. Fallback to default policy
        return default_policy

    def _is_backup_deletable_under_policy(
        self, backup: BackupInfo, all_backups: List[BackupInfo], policy: RetentionPolicy
    ) -> bool:
        """Check if a backup can be deleted while ensuring chain integrity.

        Args:
            backup: Backup to check
            all_backups: All backups for the resource
            policy: Retention policy to apply

        Returns:
            True if backup can be deleted while maintaining chain integrity
        """
        # Rule 1: Always keep at least 1 backup
        total_backups = len(all_backups)
        if total_backups <= 1:
            return False

        # Rule 2: For full backups, ensure chain integrity
        if backup.backup_type == BackupType.FULL:
            # Check if there are dependent incrementals
            if not self.can_delete_full_backup(backup):
                return False

            # Ensure at least one full backup remains after deletion
            full_backups = [b for b in all_backups if b.backup_type == BackupType.FULL]
            if len(full_backups) <= 1:
                # This is the last full backup - check if there are incrementals that need it
                incremental_backups = [
                    b for b in all_backups if b.backup_type == BackupType.INCREMENTAL
                ]
                if incremental_backups:
                    return False  # Keep the full backup for incremental chain integrity

        # Rule 3: For incremental backups, check parent chain integrity
        elif backup.backup_type == BackupType.INCREMENTAL:
            if backup.parent_backup_id:
                parent_exists = any(
                    b.backup_id == backup.parent_backup_id for b in all_backups
                )
                if not parent_exists:
                    # Parent is gone, this incremental is orphaned and can be deleted
                    return True

                # Check if deleting this incremental would orphan other incrementals
                dependent_incrementals = [
                    b
                    for b in all_backups
                    if b.backup_type == BackupType.INCREMENTAL
                    and b.parent_backup_id == backup.backup_id
                ]
                if dependent_incrementals:
                    return (
                        False  # Don't delete if other incrementals depend on this one
                    )

        # Rule 4: Snapshots can always be deleted (they don't affect chains)
        elif backup.backup_type == BackupType.SNAPSHOT:
            return True

        return True

    def _ensure_chain_integrity_after_deletion(
        self, backup_to_delete: BackupInfo, all_backups: List[BackupInfo]
    ) -> bool:
        """Ensure that deleting a backup won't break backup chains.

        Args:
            backup_to_delete: Backup that would be deleted
            all_backups: All backups for the resource

        Returns:
            True if deletion is safe for chain integrity
        """
        # Simulate deletion
        remaining_backups = [
            b for b in all_backups if b.backup_id != backup_to_delete.backup_id
        ]

        # Check that all remaining incrementals have valid parents
        for backup in remaining_backups:
            if backup.backup_type == BackupType.INCREMENTAL and backup.parent_backup_id:
                parent_exists = any(
                    b.backup_id == backup.parent_backup_id for b in remaining_backups
                )
                if not parent_exists:
                    self.logger.warning(
                        f"Deleting {backup_to_delete.backup_id} would orphan incremental {backup.backup_id}"
                    )
                    return False

        # Ensure at least one full backup remains if there are incrementals
        remaining_full_backups = [
            b for b in remaining_backups if b.backup_type == BackupType.FULL
        ]
        remaining_incrementals = [
            b for b in remaining_backups if b.backup_type == BackupType.INCREMENTAL
        ]

        if remaining_incrementals and not remaining_full_backups:
            self.logger.warning(
                f"Deleting {backup_to_delete.backup_id} would leave incrementals without any full backup"
            )
            return False

        return True

    async def _delete_backup_with_result(self, backup_info: BackupInfo) -> bool:
        """Helper method for batch deletion that returns boolean result.

        Args:
            backup_info: Backup to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            return await self.delete_backup(backup_info)
        except Exception as e:
            self.logger.error(
                f"Exception in _delete_backup_with_result for {backup_info.backup_id}: {e}"
            )
            raise  # Re-raise for gather() to catch

    async def delete_backup_chain_aware(
        self, backup_info: BackupInfo, force: bool = False
    ) -> Dict[str, any]:
        """Delete a backup while maintaining chain integrity.

        Args:
            backup_info: Backup to delete
            force: If True, delete even if it breaks chains (delete dependents first)

        Returns:
            Dictionary with deletion results
        """
        deletion_result = {
            "success": False,
            "backup_id": backup_info.backup_id,
            "deleted_backups": [],
            "failed_deletions": [],
            "warnings": [],
            "chain_impact": None,
        }

        # First, validate if deletion is safe
        safety_check = self.validate_deletion_safety(backup_info)

        if not safety_check["safe"] and not force:
            deletion_result["warnings"].extend(safety_check["errors"])
            deletion_result["warnings"].append(
                "Deletion aborted due to safety concerns (use force=True to override)"
            )
            return deletion_result

        try:
            # If this is a full backup with dependents and force=True, delete dependents first
            if (
                backup_info.backup_type == BackupType.FULL
                and safety_check["dependent_backups"]
                and force
            ):

                self.logger.warning(
                    f"Force deleting full backup {backup_info.backup_id} with {len(safety_check['dependent_backups'])} dependents"
                )

                # Get all dependent backups
                dependents = self.state_manager.get_dependent_incrementals(
                    backup_info.backup_id
                )

                # Sort dependents by creation date (newest first to avoid breaking chains)
                dependents.sort(
                    key=lambda b: b.created_at or self._get_min_datetime(), reverse=True
                )

                # Delete all dependents first
                for dependent in dependents:
                    if await self.delete_backup(dependent):
                        deletion_result["deleted_backups"].append(
                            {
                                "backup_id": dependent.backup_id,
                                "backup_type": dependent.backup_type.value,
                                "reason": "dependent_of_deleted_full_backup",
                            }
                        )
                        self.logger.info(
                            f"Deleted dependent backup {dependent.backup_id}"
                        )
                    else:
                        deletion_result["failed_deletions"].append(
                            {
                                "backup_id": dependent.backup_id,
                                "backup_type": dependent.backup_type.value,
                                "reason": "failed_to_delete_dependent",
                            }
                        )
                        self.logger.error(
                            f"Failed to delete dependent backup {dependent.backup_id}"
                        )

            # Now delete the main backup
            if await self.delete_backup(backup_info):
                deletion_result["success"] = True
                deletion_result["deleted_backups"].append(
                    {
                        "backup_id": backup_info.backup_id,
                        "backup_type": backup_info.backup_type.value,
                        "reason": "primary_target",
                    }
                )

                # Record chain impact
                if backup_info.backup_type == BackupType.FULL:
                    deletion_result["chain_impact"] = "full_backup_deleted"
                elif backup_info.backup_type == BackupType.INCREMENTAL:
                    deletion_result["chain_impact"] = "incremental_backup_deleted"
                else:
                    deletion_result["chain_impact"] = "snapshot_deleted"

            else:
                deletion_result["failed_deletions"].append(
                    {
                        "backup_id": backup_info.backup_id,
                        "backup_type": backup_info.backup_type.value,
                        "reason": "primary_deletion_failed",
                    }
                )

        except Exception as e:
            self.logger.error(
                f"Exception during chain-aware deletion of {backup_info.backup_id}: {e}"
            )
            deletion_result["warnings"].append(f"Exception during deletion: {str(e)}")

        return deletion_result

    async def cleanup_backup_chain(
        self, resource_id: str, retention_policy: RetentionPolicy
    ) -> Dict[str, any]:
        """Clean up an entire backup chain for a resource while maintaining integrity.

        Args:
            resource_id: ID of the resource
            retention_policy: Retention policy to apply

        Returns:
            Dictionary with cleanup results
        """
        cleanup_result = {
            "resource_id": resource_id,
            "success": True,
            "deleted_backups": [],
            "failed_deletions": [],
            "warnings": [],
            "chains_processed": 0,
            "space_freed_bytes": 0,
        }

        try:
            # Get all backups for the resource
            all_backups = self.state_manager.get_backup_chain(resource_id)

            if not all_backups:
                cleanup_result["warnings"].append("No backups found for resource")
                return cleanup_result

            self.logger.info(
                f"Starting chain cleanup for resource {resource_id} with {len(all_backups)} backups"
            )

            # Get backups to delete based on retention policy
            old_backups = self.state_manager.get_backups_older_than(
                retention_policy.retention_days
            )
            resource_old_backups = [
                b for b in old_backups if b.resource_id == resource_id
            ]

            # Apply retention rules
            deletable_backups = self._apply_retention_rules(
                resource_old_backups, all_backups, retention_policy
            )

            if not deletable_backups:
                cleanup_result["warnings"].append("No backups eligible for deletion")
                return cleanup_result

            # Group deletable backups by chain (full backup roots)
            chains_to_process = self._group_backups_by_chain(
                deletable_backups, all_backups
            )
            cleanup_result["chains_processed"] = len(chains_to_process)

            # Process each chain
            for chain_root, chain_backups in chains_to_process.items():
                chain_result = await self._cleanup_single_chain(
                    chain_root, chain_backups, retention_policy
                )

                # Merge results
                cleanup_result["deleted_backups"].extend(
                    chain_result["deleted_backups"]
                )
                cleanup_result["failed_deletions"].extend(
                    chain_result["failed_deletions"]
                )
                cleanup_result["warnings"].extend(chain_result["warnings"])
                cleanup_result["space_freed_bytes"] += chain_result.get(
                    "space_freed_bytes", 0
                )

                if not chain_result["success"]:
                    cleanup_result["success"] = False

            self.logger.info(
                f"Chain cleanup completed for resource {resource_id}: "
                f"{len(cleanup_result['deleted_backups'])} deleted, "
                f"{len(cleanup_result['failed_deletions'])} failed"
            )

        except Exception as e:
            self.logger.error(
                f"Exception during chain cleanup for resource {resource_id}: {e}"
            )
            cleanup_result["success"] = False
            cleanup_result["warnings"].append(f"Exception during cleanup: {str(e)}")

        return cleanup_result

    def _group_backups_by_chain(
        self, deletable_backups: List[BackupInfo], all_backups: List[BackupInfo]
    ) -> Dict[Optional[str], List[BackupInfo]]:
        """Group deletable backups by their chain root (full backup).

        Args:
            deletable_backups: Backups that can be deleted
            all_backups: All backups for the resource

        Returns:
            Dictionary mapping chain root backup IDs to lists of deletable backups in that chain
        """
        chains = {}

        for backup in deletable_backups:
            # Find the root of this backup's chain
            chain_root = self._find_chain_root(backup, all_backups)

            if chain_root not in chains:
                chains[chain_root] = []

            chains[chain_root].append(backup)

        return chains

    def _find_chain_root(
        self, backup: BackupInfo, all_backups: List[BackupInfo]
    ) -> Optional[str]:
        """Find the root (full backup) of a backup's chain.

        Args:
            backup: Backup to find root for
            all_backups: All backups for the resource

        Returns:
            Backup ID of the chain root, or None if it's a standalone backup
        """
        if backup.backup_type == BackupType.FULL:
            return backup.backup_id

        if backup.backup_type == BackupType.SNAPSHOT:
            return None  # Snapshots are standalone

        # For incremental backups, trace back to the full backup
        current = backup
        visited = set()

        while current and current.backup_id not in visited:
            visited.add(current.backup_id)

            if current.backup_type == BackupType.FULL:
                return current.backup_id

            if not current.parent_backup_id:
                break

            # Find parent backup
            parent = None
            for b in all_backups:
                if b.backup_id == current.parent_backup_id:
                    parent = b
                    break

            current = parent

        return None  # Orphaned or circular reference

    async def _cleanup_single_chain(
        self,
        chain_root: Optional[str],
        chain_backups: List[BackupInfo],
        retention_policy: RetentionPolicy,
    ) -> Dict[str, any]:
        """Clean up a single backup chain.

        Args:
            chain_root: Root backup ID of the chain (None for standalone backups)
            chain_backups: Backups in this chain that are eligible for deletion
            retention_policy: Retention policy to apply

        Returns:
            Dictionary with cleanup results for this chain
        """
        chain_result = {
            "success": True,
            "chain_root": chain_root,
            "deleted_backups": [],
            "failed_deletions": [],
            "warnings": [],
            "space_freed_bytes": 0,
        }

        # Sort backups by creation date (newest first to maintain chain integrity)
        chain_backups.sort(
            key=lambda b: b.created_at or self._get_min_datetime(), reverse=True
        )

        for backup in chain_backups:
            try:
                # Calculate space that will be freed
                space_to_free = backup.size_bytes or 0

                # Perform chain-aware deletion
                deletion_result = await self.delete_backup_chain_aware(
                    backup, force=False
                )

                if deletion_result["success"]:
                    chain_result["deleted_backups"].extend(
                        deletion_result["deleted_backups"]
                    )
                    chain_result["space_freed_bytes"] += space_to_free
                else:
                    chain_result["failed_deletions"].extend(
                        deletion_result["failed_deletions"]
                    )
                    chain_result["success"] = False

                chain_result["warnings"].extend(deletion_result["warnings"])

            except Exception as e:
                self.logger.error(
                    f"Exception while cleaning up backup {backup.backup_id}: {e}"
                )
                chain_result["failed_deletions"].append(
                    {
                        "backup_id": backup.backup_id,
                        "backup_type": backup.backup_type.value,
                        "reason": f"exception: {str(e)}",
                    }
                )
                chain_result["success"] = False

        return chain_result

    async def repair_broken_chains(
        self, resource_id: str, dry_run: bool = True
    ) -> Dict[str, any]:
        """Repair broken backup chains by removing orphaned backups.

        Args:
            resource_id: ID of the resource
            dry_run: If True, only report what would be done

        Returns:
            Dictionary with repair results
        """
        repair_result = {
            "resource_id": resource_id,
            "dry_run": dry_run,
            "success": True,
            "orphaned_backups": [],
            "repaired_chains": [],
            "deleted_backups": [],
            "warnings": [],
        }

        try:
            # Get all backups for the resource
            all_backups = self.state_manager.get_backup_chain(resource_id)

            if not all_backups:
                repair_result["warnings"].append("No backups found for resource")
                return repair_result

            # Find orphaned backups (incrementals with missing parents)
            orphaned = []
            backup_ids = {b.backup_id for b in all_backups}

            for backup in all_backups:
                if (
                    backup.backup_type == BackupType.INCREMENTAL
                    and backup.parent_backup_id
                    and backup.parent_backup_id not in backup_ids
                ):
                    orphaned.append(backup)

            repair_result["orphaned_backups"] = [
                {
                    "backup_id": b.backup_id,
                    "missing_parent_id": b.parent_backup_id,
                    "created_at": b.created_at,
                }
                for b in orphaned
            ]

            if not orphaned:
                repair_result["warnings"].append("No orphaned backups found")
                return repair_result

            self.logger.info(
                f"Found {len(orphaned)} orphaned backups for resource {resource_id}"
            )

            # Remove orphaned backups
            if not dry_run:
                for orphaned_backup in orphaned:
                    if await self.delete_backup(orphaned_backup):
                        repair_result["deleted_backups"].append(
                            {
                                "backup_id": orphaned_backup.backup_id,
                                "reason": "orphaned_incremental",
                            }
                        )
                        self.logger.info(
                            f"Removed orphaned backup {orphaned_backup.backup_id}"
                        )
                    else:
                        repair_result["success"] = False
                        self.logger.error(
                            f"Failed to remove orphaned backup {orphaned_backup.backup_id}"
                        )

            # Analyze remaining chains
            remaining_backups = (
                [b for b in all_backups if b not in orphaned]
                if not dry_run
                else all_backups
            )
            chain_analysis = self._analyze_chain_structure(remaining_backups)
            repair_result["repaired_chains"] = chain_analysis

        except Exception as e:
            self.logger.error(
                f"Exception during chain repair for resource {resource_id}: {e}"
            )
            repair_result["success"] = False
            repair_result["warnings"].append(f"Exception during repair: {str(e)}")

        return repair_result

    def _analyze_chain_structure(
        self, backups: List[BackupInfo]
    ) -> List[Dict[str, any]]:
        """Analyze the structure of backup chains.

        Args:
            backups: List of backups to analyze

        Returns:
            List of chain analysis results
        """
        chains = []

        # Find all full backups (chain roots)
        full_backups = [b for b in backups if b.backup_type == BackupType.FULL]

        for full_backup in full_backups:
            # Find all incrementals that belong to this chain
            chain_incrementals = []

            for backup in backups:
                if backup.backup_type == BackupType.INCREMENTAL:
                    root = self._find_chain_root(backup, backups)
                    if root == full_backup.backup_id:
                        chain_incrementals.append(backup)

            chain_info = {
                "root_backup_id": full_backup.backup_id,
                "root_created_at": full_backup.created_at,
                "incremental_count": len(chain_incrementals),
                "chain_length": 1 + len(chain_incrementals),
                "is_complete": True,  # All incrementals have valid parents
                "total_size_bytes": (full_backup.size_bytes or 0)
                + sum(i.size_bytes or 0 for i in chain_incrementals),
            }

            chains.append(chain_info)

        return chains

    def _extract_retention_from_tag(self, schedule_tag: str) -> Optional[int]:
        """Extract retention days from schedule tag.

        Args:
            schedule_tag: Schedule tag like 'SNAPSHOT-DAILY-0300-RETAIN14'

        Returns:
            Retention days if found in tag, None otherwise
        """
        import re

        # Look for RETAIN followed by digits
        match = re.search(r"RETAIN(\d+)", schedule_tag)
        if match:
            return int(match.group(1))
        return None

    def _get_backups_to_delete_with_retention(
        self, backups: List[BackupInfo], retention_days: int
    ) -> List[BackupInfo]:
        """Get backups to delete based on specific retention days.

        Args:
            backups: List of backups to evaluate
            retention_days: Number of days to retain backups

        Returns:
            List of backups that should be deleted
        """
        if not backups:
            return []

        candidates = []
        now = self._get_now()

        for backup in backups:
            if backup.created_at:
                # Ensure both datetimes are timezone-aware
                backup_time = backup.created_at
                if backup_time.tzinfo is None:
                    backup_time = backup_time.replace(tzinfo=self.tz)

                age_days = (now - backup_time).days
                if age_days > retention_days:
                    candidates.append(backup)
                    self.logger.debug(
                        f"Backup {backup.backup_id} is {age_days} days old "
                        f"(retention: {retention_days} days) - marked for deletion"
                    )

        return candidates

    def _get_backups_to_delete_from_list(
        self, backups: List[BackupInfo], retention_days: int
    ) -> List[BackupInfo]:
        """Get backups to delete from a specific list (fallback method).

        Args:
            backups: List of backups to evaluate
            retention_days: Number of days to retain backups

        Returns:
            List of backups that should be deleted
        """
        return self._get_backups_to_delete_with_retention(backups, retention_days)

    def get_retention_days_for_backup_type(
        self, backup_type: BackupType, retention_policies: Dict[str, RetentionPolicy]
    ) -> int:
        """Get retention days based on backup type.

        Args:
            backup_type: The type of backup (SNAPSHOT, BACKUP, etc.)
            retention_policies: Dictionary of retention policies

        Returns:
            Number of retention days for this backup type
        """
        if backup_type == BackupType.SNAPSHOT:
            # Use snapshots policy if available, otherwise default
            policy = retention_policies.get(
                "snapshots", retention_policies.get("default")
            )
            return policy.retention_days if policy else 7
        elif backup_type in [BackupType.FULL, BackupType.INCREMENTAL]:
            # Use default policy for volume backups
            policy = retention_policies.get("default")
            return policy.retention_days if policy else 30
        else:
            # Fallback to default policy for unknown types
            policy = retention_policies.get("default")
            return policy.retention_days if policy else 30

    async def _delete_related_volume_snapshots(self, instance_snapshot_id: str) -> int:
        """Delete all volume snapshots related to an instance snapshot.

        Args:
            instance_snapshot_id: ID of the instance snapshot

        Returns:
            Number of successfully deleted volume snapshots
        """
        deleted_count = 0
        try:
            # Find all volume snapshots related to this instance snapshot
            all_backups = self.state_manager.get_all_backups()
            related_snapshots = [
                b
                for b in all_backups
                if b.related_instance_snapshot_id == instance_snapshot_id
            ]

            if not related_snapshots:
                self.logger.debug(
                    f"No related volume snapshots found for instance snapshot {instance_snapshot_id}"
                )
                return 0

            self.logger.info(
                f"Found {len(related_snapshots)} related volume snapshots for instance snapshot {instance_snapshot_id}"
            )

            # Delete each related volume snapshot
            for volume_snapshot in related_snapshots:
                try:
                    self.logger.info(
                        f"Deleting related volume snapshot {volume_snapshot.backup_id} "
                        f"for volume {volume_snapshot.resource_id}"
                    )

                    success = await self.openstack_client.delete_snapshot(
                        volume_snapshot.backup_id, "volume"
                    )

                    if success:
                        self.logger.info(
                            f"Successfully deleted related volume snapshot {volume_snapshot.backup_id}"
                        )
                        # Only delete DB record if OpenStack deletion was successful
                        self.state_manager.delete_backup_record(
                            volume_snapshot.backup_id
                        )
                        deleted_count += 1
                    else:
                        self.logger.error(
                            f"Failed to delete related volume snapshot {volume_snapshot.backup_id}"
                        )

                except Exception as e:
                    self.logger.error(
                        f"Exception while deleting related volume snapshot {volume_snapshot.backup_id}: {e}"
                    )

            return deleted_count

        except Exception as e:
            self.logger.error(
                f"Exception while deleting related volume snapshots for instance snapshot {instance_snapshot_id}: {e}"
            )
            return deleted_count
