"""Tests for configuration manager - critical functionality only."""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch

# Add the src directory to the path to avoid circular imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config.manager import ConfigurationManager
from config.models import AuthMethod


class TestConfigurationManager:
    """Test critical configuration manager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config_manager = ConfigurationManager()

    def create_temp_config_file(self, content: str) -> str:
        """Create a temporary configuration file with given content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(content)
            return f.name

    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        config_content = """
openstack:
  auth_method: "application_credential"
  auth_url: "https://openstack.example.com:5000/v3"
  project_name: "test-project"
  application_credential_id: "test-id"
  application_credential_secret: "test-secret"

notifications:
  email_recipient: "admin@example.com"
  email_sender: "backup@example.com"

database_path: "./test_backup.db"
"""
        config_file = self.create_temp_config_file(config_content)
        
        try:
            config = self.config_manager.load_config(config_file)
            assert config.openstack.auth_method == AuthMethod.APPLICATION_CREDENTIAL
            assert config.openstack.auth_url == "https://openstack.example.com:5000/v3"
        finally:
            os.unlink(config_file)

    def test_environment_variable_substitution(self):
        """Test environment variable substitution - core functionality."""
        config_content = """
openstack:
  auth_method: "application_credential"
  auth_url: "${AUTH_URL}"
  project_name: "test-project"
  application_credential_id: "${APP_CRED_ID}"
  application_credential_secret: "${APP_CRED_SECRET}"

notifications:
  email_recipient: "admin@example.com"
  email_sender: "backup@example.com"

database_path: "./test_backup.db"
"""
        config_file = self.create_temp_config_file(config_content)
        
        env_vars = {
            'AUTH_URL': 'https://test.openstack.com:5000/v3',
            'APP_CRED_ID': 'test-app-cred-id',
            'APP_CRED_SECRET': 'test-app-cred-secret',
        }
        
        try:
            with patch.dict(os.environ, env_vars, clear=False):
                config = self.config_manager.load_config(config_file)
                assert config.openstack.auth_url == "https://test.openstack.com:5000/v3"
        finally:
            os.unlink(config_file)