#!/usr/bin/env python3
"""Test script to debug retention logic."""

import asyncio
import sys
from src.factory import create_coordinator_from_config

async def test_retention():
    """Test retention logic directly."""
    try:
        # Create coordinator
        coordinator = create_coordinator_from_config("config.yaml")
        
        # Get retention manager
        retention_manager = coordinator.retention_manager
        
        print("=== Testing Retention Logic ===")
        
        # Test with current config
        retention_policies = coordinator.config.retention_policies
        backup_config = coordinator.config.backup
        
        print(f"Retention policies: {retention_policies}")
        print(f"Backup config - snapshot_retention_days: {backup_config.snapshot_retention_days}")
        print(f"Backup config - backup_retention_days: {backup_config.backup_retention_days}")
        
        # Get backups to delete
        backups_to_delete = retention_manager.get_backups_to_delete_with_tag_policies(
            retention_policies.get("default"),
            retention_policies,
            backup_config
        )
        
        print(f"\nBackups to delete: {len(backups_to_delete)}")
        for backup in backups_to_delete:
            age_days = retention_manager.calculate_backup_age(backup)
            print(f"  - {backup.backup_id}: {backup.backup_type.value}, age: {age_days} days, created: {backup.created_at}")
        
        # Also test direct method
        print("\n=== Testing get_backups_older_than directly ===")
        old_backups_1_day = retention_manager.state_manager.get_backups_older_than(1)
        print(f"Backups older than 1 day: {len(old_backups_1_day)}")
        for backup in old_backups_1_day:
            age_days = retention_manager.calculate_backup_age(backup)
            print(f"  - {backup.backup_id}: {backup.backup_type.value}, age: {age_days} days, created: {backup.created_at}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_retention())