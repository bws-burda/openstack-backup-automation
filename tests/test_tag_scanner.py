"""Tests for tag scanner - critical functionality only."""

import pytest
from unittest.mock import AsyncMock

from src.scanner.tag_scanner import TagScanner
from src.scanner.models import OperationType, Frequency, ResourceType


class TestTagScanner:
    """Test critical tag scanner functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = AsyncMock()
        self.scanner = TagScanner(self.mock_client)

    def test_parse_valid_schedule_tags(self):
        """Test parsing of valid schedule tags."""
        test_cases = [
            ("BACKUP-DAILY-0300", OperationType.BACKUP, Frequency.DAILY, "0300"),
            ("SNAPSHOT-WEEKLY-1200", OperationType.SNAPSHOT, Frequency.WEEKLY, "1200"),
        ]

        for tag, expected_type, expected_freq, expected_time in test_cases:
            result = self.scanner.parse_schedule_tag(tag)
            assert result is not None
            assert result.operation_type == expected_type
            assert result.frequency == expected_freq
            assert result.time == expected_time

    def test_parse_invalid_schedule_tags(self):
        """Test parsing of invalid schedule tags."""
        invalid_tags = ["", "INVALID-DAILY-0300", "BACKUP-DAILY-2500"]

        for tag in invalid_tags:
            result = self.scanner.parse_schedule_tag(tag)
            assert result is None

    @pytest.mark.asyncio
    async def test_scan_instances_success(self):
        """Test successful instance scanning."""
        mock_instances = [
            {"id": "instance-1", "name": "test-instance", "tags": ["BACKUP-DAILY-0300"]}
        ]
        
        self.mock_client.get_instances_with_tags.return_value = mock_instances
        result = await self.scanner.scan_instances()
        
        assert len(result) == 1
        assert result[0].id == "instance-1"
        assert result[0].type == ResourceType.INSTANCE

    @pytest.mark.asyncio
    async def test_scan_volumes_success(self):
        """Test successful volume scanning."""
        mock_volumes = [
            {"id": "volume-1", "name": "test-volume", "tags": ["BACKUP-MONTHLY-0200"], "metadata": {}}
        ]
        
        self.mock_client.get_volumes_with_tags.return_value = mock_volumes
        result = await self.scanner.scan_volumes()
        
        assert len(result) == 1
        assert result[0].id == "volume-1"
        assert result[0].type == ResourceType.VOLUME