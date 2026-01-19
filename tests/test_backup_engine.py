"""Tests for backup engine - critical functionality only."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.backup.engine import BackupEngine
from src.backup.models import BackupOperation, BackupType, OperationStatus


class TestBackupEngine:
    """Test critical backup engine functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = AsyncMock()
        self.mock_state_manager = MagicMock()
        self.engine = BackupEngine(
            openstack_client=self.mock_client,
            state_manager=self.mock_state_manager,
            max_concurrent_operations=2,
            operation_timeout_minutes=30
        )

    @pytest.mark.asyncio
    async def test_create_instance_snapshot(self):
        """Test instance snapshot creation."""
        self.mock_client.create_instance_snapshot.return_value = "snapshot-123"
        
        result = await self.engine.create_instance_snapshot("instance-1", "test-snapshot")
        
        assert result == "snapshot-123"
        self.mock_client.create_instance_snapshot.assert_called_once_with("instance-1", "test-snapshot")

    @pytest.mark.asyncio
    async def test_create_volume_backup(self):
        """Test volume backup creation."""
        self.mock_client.get_volume.return_value = {"id": "volume-1", "status": "available"}
        self.mock_client.create_volume_backup.return_value = "backup-456"
        
        result = await self.engine.create_volume_backup("volume-1", "test-backup", "full")
        
        assert result == "backup-456"
        self.mock_client.create_volume_backup.assert_called_once_with(
            "volume-1", "test-backup", False, None
        )

    @pytest.mark.asyncio
    async def test_verify_backup_success(self):
        """Test backup verification."""
        self.mock_client.get_backup_status.return_value = "available"
        
        result = await self.engine.verify_backup_success("backup-123", "volume", 1)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_parallel_operations(self):
        """Test parallel operation execution."""
        operations = [
            BackupOperation(
                resource_id="instance-1",
                resource_type="instance",
                resource_name="test-instance",
                operation_type=BackupType.SNAPSHOT,
                schedule_tag="SNAPSHOT-DAILY-0300",
                timeout_minutes=30
            )
        ]
        
        self.mock_client.create_instance_snapshot.return_value = "snapshot-123"
        self.mock_client.get_backup_status.return_value = "available"
        
        results = await self.engine.execute_parallel_operations(operations)
        
        assert len(results) == 1
        assert results[0].status == OperationStatus.COMPLETED
        assert results[0].backup_info is not None