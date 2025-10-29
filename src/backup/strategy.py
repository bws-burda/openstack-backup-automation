"""Backup strategy logic for determining full vs incremental backups."""

import logging
from datetime import datetime, timedelta, UTC
from typing import TYPE_CHECKING, Optional

from .chain_manager import BackupChainManager
from .models import BackupInfo, BackupType

if TYPE_CHECKING:
    from ..interfaces import StateManagerInterface


class BackupStrategy:
    """Determines backup type and manages backup strategy logic."""

    def __init__(
        self,
        state_manager: "StateManagerInterface",
        full_backup_interval_days: int = 7,
    ):
        """Initialize backup strategy.
        
        Args:
            state_manager: State manager for backup history
            full_backup_interval_days: Days between full backups
        """
        self.state_manager = state_manager
        self.full_backup_interval_days = full_backup_interval_days
        self.logger = logging.getLogger(__name__)
        
        # Initialize chain manager
        self.chain_manager = BackupChainManager(state_manager)

    def determine_backup_type(self, resource_id: str) -> BackupType:
        """Determine whether to create a full or incremental backup.
        
        Args:
            resource_id: ID of the resource to backup
            
        Returns:
            BackupType indicating whether to create full or incremental backup
        """
        # Get the last full backup for this resource
        last_full_backup = self.state_manager.get_last_full_backup(resource_id)
        
        # If no full backup exists, create one
        if not last_full_backup:
            self.logger.info(f"No full backup found for resource {resource_id}, creating full backup")
            return BackupType.FULL
        
        # Check if it's time for a new full backup based on interval
        if self._is_full_backup_due(last_full_backup):
            self.logger.info(
                f"Full backup interval ({self.full_backup_interval_days} days) reached "
                f"for resource {resource_id}, creating full backup"
            )
            return BackupType.FULL
        
        # Otherwise, create incremental backup
        self.logger.info(f"Creating incremental backup for resource {resource_id}")
        return BackupType.INCREMENTAL

    def get_parent_backup_id(self, resource_id: str, backup_type: BackupType) -> Optional[str]:
        """Get the parent backup ID for incremental backups.
        
        Args:
            resource_id: ID of the resource
            backup_type: Type of backup being created
            
        Returns:
            Parent backup ID for incremental backups, None for full backups
        """
        if backup_type == BackupType.FULL:
            return None
        
        # For incremental backups, find the most recent backup (full or incremental)
        last_backup = self.state_manager.get_last_backup(resource_id)
        
        if last_backup and last_backup.verified:
            self.logger.debug(
                f"Using parent backup {last_backup.backup_id} for incremental backup "
                f"of resource {resource_id}"
            )
            return last_backup.backup_id
        
        # If no verified backup exists, we need a full backup instead
        self.logger.warning(
            f"No verified parent backup found for resource {resource_id}, "
            "full backup required"
        )
        return None

    def validate_backup_chain_integrity(self, resource_id: str) -> bool:
        """Validate the integrity of the backup chain for a resource.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            True if backup chain is valid, False otherwise
        """
        validation_result = self.chain_manager.validate_chain_structure(resource_id)
        
        if not validation_result["valid"]:
            for error in validation_result["errors"]:
                self.logger.error(f"Chain validation error for resource {resource_id}: {error}")
        
        return validation_result["valid"]

    def get_backup_chain_summary(self, resource_id: str) -> dict:
        """Get a summary of the backup chain for a resource.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            Dictionary with backup chain statistics
        """
        return self.chain_manager.get_chain_statistics(resource_id)

    def _is_full_backup_due(self, last_full_backup: BackupInfo) -> bool:
        """Check if a full backup is due based on the interval.
        
        Args:
            last_full_backup: Information about the last full backup
            
        Returns:
            True if a full backup is due, False otherwise
        """
        if not last_full_backup.created_at:
            return True
        
        days_since_full = (datetime.now(UTC) - last_full_backup.created_at).days
        return days_since_full >= self.full_backup_interval_days

    def calculate_next_full_backup_date(self, resource_id: str) -> Optional[datetime]:
        """Calculate when the next full backup should be created.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            Datetime when next full backup is due, None if no previous full backup
        """
        last_full_backup = self.state_manager.get_last_full_backup(resource_id)
        
        if not last_full_backup or not last_full_backup.created_at:
            return None
        
        return last_full_backup.created_at + timedelta(days=self.full_backup_interval_days)

    def should_create_backup(self, resource_id: str, backup_type: BackupType) -> bool:
        """Determine if a backup should be created based on strategy rules.
        
        Args:
            resource_id: ID of the resource
            backup_type: Type of backup to create
            
        Returns:
            True if backup should be created, False otherwise
        """
        # Always allow snapshots
        if backup_type == BackupType.SNAPSHOT:
            return True
        
        # For full backups, check if one is due
        if backup_type == BackupType.FULL:
            last_full_backup = self.state_manager.get_last_full_backup(resource_id)
            return last_full_backup is None or self._is_full_backup_due(last_full_backup)
        
        # For incremental backups, ensure we have a valid parent
        if backup_type == BackupType.INCREMENTAL:
            parent_id = self.get_parent_backup_id(resource_id, backup_type)
            return parent_id is not None
        
        return False

    def get_chain_manager(self) -> BackupChainManager:
        """Get the backup chain manager instance.
        
        Returns:
            BackupChainManager instance
        """
        return self.chain_manager

    def find_orphaned_backups(self, resource_id: str) -> list:
        """Find backups that reference non-existent parents.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            List of orphaned backup info objects
        """
        return self.chain_manager.find_orphaned_backups(resource_id)

    def can_safely_delete_backup(self, backup_id: str) -> dict:
        """Check if a backup can be safely deleted without breaking chains.
        
        Args:
            backup_id: ID of the backup to check
            
        Returns:
            Dictionary with safety check results
        """
        return self.chain_manager.can_safely_delete_backup(backup_id)

    def repair_chain_integrity(self, resource_id: str, dry_run: bool = True) -> dict:
        """Attempt to repair backup chain integrity issues.
        
        Args:
            resource_id: ID of the resource
            dry_run: If True, only report what would be done without making changes
            
        Returns:
            Dictionary with repair actions taken or planned
        """
        return self.chain_manager.repair_chain_integrity(resource_id, dry_run)

    def get_chain_roots(self, resource_id: str) -> list:
        """Get all root backups (full backups with no parents) for a resource.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            List of root backup info objects
        """
        return self.chain_manager.get_chain_roots(resource_id)

    def get_chain_descendants(self, backup_id: str) -> list:
        """Get all descendants (children, grandchildren, etc.) of a backup.
        
        Args:
            backup_id: ID of the parent backup
            
        Returns:
            List of descendant backup info objects
        """
        return self.chain_manager.get_chain_descendants(backup_id)