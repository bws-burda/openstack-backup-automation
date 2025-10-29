"""Backup chain management for tracking parent-child relationships."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from .models import BackupInfo, BackupType

if TYPE_CHECKING:
    from ..interfaces import StateManagerInterface


class BackupChainManager:
    """Manages backup chains and ensures integrity of parent-child relationships."""

    def __init__(self, state_manager: "StateManagerInterface"):
        """Initialize backup chain manager.
        
        Args:
            state_manager: State manager for backup history
        """
        self.state_manager = state_manager
        self.logger = logging.getLogger(__name__)

    def build_chain_graph(self, resource_id: str) -> Dict[str, List[str]]:
        """Build a graph representation of the backup chain.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            Dictionary mapping backup IDs to their children
        """
        backup_chain = self.state_manager.get_backup_chain(resource_id)
        
        # Build parent -> children mapping
        chain_graph = {}
        
        for backup in backup_chain:
            # Initialize entry for this backup
            if backup.backup_id not in chain_graph:
                chain_graph[backup.backup_id] = []
            
            # Add this backup as child of its parent
            if backup.parent_backup_id:
                if backup.parent_backup_id not in chain_graph:
                    chain_graph[backup.parent_backup_id] = []
                chain_graph[backup.parent_backup_id].append(backup.backup_id)
        
        return chain_graph

    def get_chain_roots(self, resource_id: str) -> List[BackupInfo]:
        """Get all root backups (full backups with no parents) for a resource.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            List of root backup info objects
        """
        backup_chain = self.state_manager.get_backup_chain(resource_id)
        
        roots = []
        for backup in backup_chain:
            if backup.backup_type == BackupType.FULL and backup.parent_backup_id is None:
                roots.append(backup)
        
        # Sort by creation time
        roots.sort(key=lambda b: b.created_at or datetime.min)
        return roots

    def get_chain_descendants(self, backup_id: str) -> List[BackupInfo]:
        """Get all descendants (children, grandchildren, etc.) of a backup.
        
        Args:
            backup_id: ID of the parent backup
            
        Returns:
            List of descendant backup info objects
        """
        return self.state_manager.get_dependent_incrementals(backup_id)

    def find_orphaned_backups(self, resource_id: str) -> List[BackupInfo]:
        """Find backups that reference non-existent parents.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            List of orphaned backup info objects
        """
        backup_chain = self.state_manager.get_backup_chain(resource_id)
        
        # Create set of all backup IDs
        existing_ids = {backup.backup_id for backup in backup_chain}
        
        orphaned = []
        for backup in backup_chain:
            if (backup.parent_backup_id and 
                backup.parent_backup_id not in existing_ids):
                orphaned.append(backup)
                self.logger.warning(
                    f"Found orphaned backup {backup.backup_id} with missing parent "
                    f"{backup.parent_backup_id}"
                )
        
        return orphaned

    def validate_chain_structure(self, resource_id: str) -> Dict[str, any]:
        """Validate the structure of backup chains for a resource.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            Dictionary with validation results and details
        """
        backup_chain = self.state_manager.get_backup_chain(resource_id)
        
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "chain_count": 0,
            "orphaned_backups": [],
            "circular_references": [],
        }
        
        if not backup_chain:
            return validation_result
        
        # Check for orphaned backups
        orphaned = self.find_orphaned_backups(resource_id)
        if orphaned:
            validation_result["valid"] = False
            validation_result["orphaned_backups"] = [b.backup_id for b in orphaned]
            validation_result["errors"].append(f"Found {len(orphaned)} orphaned backups")
        
        # Check for circular references
        circular_refs = self._detect_circular_references(resource_id)
        if circular_refs:
            validation_result["valid"] = False
            validation_result["circular_references"] = circular_refs
            validation_result["errors"].append(f"Found circular references: {circular_refs}")
        
        # Count valid chains (starting from full backups)
        roots = self.get_chain_roots(resource_id)
        validation_result["chain_count"] = len(roots)
        
        # Validate each chain
        for root in roots:
            chain_errors = self._validate_single_chain(root.backup_id, resource_id)
            validation_result["errors"].extend(chain_errors)
            if chain_errors:
                validation_result["valid"] = False
        
        # Check for incremental backups without full backup parents
        for backup in backup_chain:
            if backup.backup_type == BackupType.INCREMENTAL:
                if not self._has_full_backup_ancestor(backup, backup_chain):
                    validation_result["valid"] = False
                    validation_result["errors"].append(
                        f"Incremental backup {backup.backup_id} has no full backup ancestor"
                    )
        
        return validation_result

    def repair_chain_integrity(self, resource_id: str, dry_run: bool = True) -> Dict[str, any]:
        """Attempt to repair backup chain integrity issues.
        
        Args:
            resource_id: ID of the resource
            dry_run: If True, only report what would be done without making changes
            
        Returns:
            Dictionary with repair actions taken or planned
        """
        repair_result = {
            "actions_taken": [],
            "actions_planned": [],
            "orphaned_removed": 0,
            "chains_rebuilt": 0,
        }
        
        # Find orphaned backups
        orphaned = self.find_orphaned_backups(resource_id)
        
        for orphaned_backup in orphaned:
            action = f"Remove orphaned backup {orphaned_backup.backup_id}"
            
            if dry_run:
                repair_result["actions_planned"].append(action)
            else:
                try:
                    self.state_manager.delete_backup_record(orphaned_backup.backup_id)
                    repair_result["actions_taken"].append(action)
                    repair_result["orphaned_removed"] += 1
                    self.logger.info(f"Removed orphaned backup {orphaned_backup.backup_id}")
                except Exception as e:
                    self.logger.error(f"Failed to remove orphaned backup: {e}")
        
        return repair_result

    def get_chain_statistics(self, resource_id: str) -> Dict[str, any]:
        """Get detailed statistics about backup chains for a resource.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            Dictionary with chain statistics
        """
        backup_chain = self.state_manager.get_backup_chain(resource_id)
        roots = self.get_chain_roots(resource_id)
        
        stats = {
            "total_backups": len(backup_chain),
            "chain_count": len(roots),
            "full_backups": sum(1 for b in backup_chain if b.backup_type == BackupType.FULL),
            "incremental_backups": sum(1 for b in backup_chain if b.backup_type == BackupType.INCREMENTAL),
            "verified_backups": sum(1 for b in backup_chain if b.verified),
            "chains": [],
        }
        
        # Analyze each chain
        for root in roots:
            descendants = self.get_chain_descendants(root.backup_id)
            chain_info = {
                "root_backup_id": root.backup_id,
                "root_created_at": root.created_at,
                "total_backups_in_chain": 1 + len(descendants),
                "incremental_count": len(descendants),
                "latest_backup": max(
                    [root] + descendants,
                    key=lambda b: b.created_at or datetime.min
                ).created_at,
                "verified_in_chain": sum(1 for b in [root] + descendants if b.verified),
            }
            stats["chains"].append(chain_info)
        
        return stats

    def can_safely_delete_backup(self, backup_id: str) -> Dict[str, any]:
        """Check if a backup can be safely deleted without breaking chains.
        
        Args:
            backup_id: ID of the backup to check
            
        Returns:
            Dictionary with safety check results
        """
        backup_info = self.state_manager.get_backup_by_id(backup_id)
        if not backup_info:
            return {"safe": False, "reason": "Backup not found"}
        
        # Get all dependent backups
        dependents = self.get_chain_descendants(backup_id)
        
        safety_check = {
            "safe": len(dependents) == 0,
            "dependent_count": len(dependents),
            "dependent_backup_ids": [d.backup_id for d in dependents],
            "reason": "",
        }
        
        if not safety_check["safe"]:
            safety_check["reason"] = (
                f"Backup has {len(dependents)} dependent incremental backups that would be orphaned"
            )
        else:
            safety_check["reason"] = "No dependent backups found, safe to delete"
        
        return safety_check

    def _detect_circular_references(self, resource_id: str) -> List[List[str]]:
        """Detect circular references in backup chains.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            List of circular reference chains
        """
        backup_chain = self.state_manager.get_backup_chain(resource_id)
        
        # Build parent mapping
        parent_map = {}
        for backup in backup_chain:
            if backup.parent_backup_id:
                parent_map[backup.backup_id] = backup.parent_backup_id
        
        circular_refs = []
        visited = set()
        
        for backup_id in parent_map:
            if backup_id in visited:
                continue
            
            # Trace the parent chain
            current = backup_id
            path = []
            path_set = set()
            
            while current and current in parent_map:
                if current in path_set:
                    # Found circular reference
                    cycle_start = path.index(current)
                    circular_refs.append(path[cycle_start:] + [current])
                    break
                
                path.append(current)
                path_set.add(current)
                current = parent_map[current]
            
            visited.update(path_set)
        
        return circular_refs

    def _validate_single_chain(self, root_backup_id: str, resource_id: str) -> List[str]:
        """Validate a single backup chain starting from a root.
        
        Args:
            root_backup_id: ID of the root backup
            resource_id: ID of the resource
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Get the root backup
        root_backup = self.state_manager.get_backup_by_id(root_backup_id)
        if not root_backup:
            errors.append(f"Root backup {root_backup_id} not found")
            return errors
        
        # Root must be a full backup
        if root_backup.backup_type != BackupType.FULL:
            errors.append(f"Root backup {root_backup_id} is not a full backup")
        
        # Root should not have a parent
        if root_backup.parent_backup_id:
            errors.append(f"Root backup {root_backup_id} has unexpected parent")
        
        # Validate all descendants
        descendants = self.get_chain_descendants(root_backup_id)
        
        for descendant in descendants:
            # All descendants should be incremental
            if descendant.backup_type != BackupType.INCREMENTAL:
                errors.append(
                    f"Non-incremental backup {descendant.backup_id} found in chain"
                )
            
            # Each descendant should have a valid parent
            if not descendant.parent_backup_id:
                errors.append(
                    f"Incremental backup {descendant.backup_id} missing parent"
                )
        
        return errors

    def _has_full_backup_ancestor(self, backup: BackupInfo, backup_chain: List[BackupInfo]) -> bool:
        """Check if a backup has a full backup ancestor.
        
        Args:
            backup: Backup to check
            backup_chain: Complete backup chain for the resource
            
        Returns:
            True if backup has a full backup ancestor, False otherwise
        """
        if backup.backup_type == BackupType.FULL:
            return True
        
        if not backup.parent_backup_id:
            return False
        
        # Find parent backup
        parent = None
        for b in backup_chain:
            if b.backup_id == backup.parent_backup_id:
                parent = b
                break
        
        if not parent:
            return False
        
        # Recursively check parent
        return self._has_full_backup_ancestor(parent, backup_chain)