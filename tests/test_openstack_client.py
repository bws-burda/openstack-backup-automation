"""Tests for OpenStack client - critical functionality only."""

import pytest
from unittest.mock import MagicMock, patch

from src.openstack_api.client import OpenStackClient
from src.config.models import OpenStackCredentials, AuthMethod


class TestOpenStackClient:
    """Test critical OpenStack client functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = OpenStackClient()
        self.credentials = OpenStackCredentials(
            auth_method=AuthMethod.APPLICATION_CREDENTIAL,
            auth_url="https://openstack.example.com:5000/v3",
            project_name="test-project",
            application_credential_id="test-id",
            application_credential_secret="test-secret"
        )

    @patch('src.openstack_api.client.openstack.connect')
    def test_authenticate_success(self, mock_connect):
        """Test successful authentication."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        
        result = self.client.authenticate(self.credentials)
        
        assert result is True
        assert self.client.is_authenticated() is True

    @patch('src.openstack_api.client.openstack.connect')
    def test_authenticate_failure(self, mock_connect):
        """Test authentication failure."""
        mock_connect.side_effect = Exception("Auth failed")
        
        result = self.client.authenticate(self.credentials)
        
        assert result is False
        assert self.client.is_authenticated() is False

    @pytest.mark.asyncio
    async def test_get_instances_with_tags(self):
        """Test getting instances with tags."""
        mock_connection = MagicMock()
        mock_server = MagicMock()
        mock_server.to_dict.return_value = {"id": "instance-1", "name": "test"}
        mock_server.tags = ["BACKUP-DAILY-0300"]
        mock_connection.compute.servers.return_value = [mock_server]
        
        self.client.connection = mock_connection
        self.client._authenticated = True
        
        result = await self.client.get_instances_with_tags("BACKUP")
        
        assert len(result) == 1
        assert result[0]["id"] == "instance-1"

    @pytest.mark.asyncio
    async def test_create_instance_snapshot(self):
        """Test instance snapshot creation."""
        mock_connection = MagicMock()
        mock_server = MagicMock()
        mock_image = MagicMock()
        mock_image.id = "snapshot-123"
        
        mock_connection.compute.get_server.return_value = mock_server
        mock_connection.compute.create_server_image.return_value = mock_image
        
        self.client.connection = mock_connection
        self.client._authenticated = True
        
        result = await self.client.create_instance_snapshot("instance-1", "test-snapshot")
        
        assert result == "snapshot-123"