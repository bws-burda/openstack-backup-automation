"""Configuration manager implementation."""

import os
import re
from typing import Any, Dict

import yaml

from .models import (AuthMethod, BackupConfig, Config, EmailSettings,
                     OpenStackCredentials, RetentionPolicy, SchedulingConfig,
                     SchedulingMode)


class ConfigurationManager:
    """Manages system configuration loading and validation."""

    def __init__(self):
        self._config: Config = None

    def _substitute_environment_variables(self, data: Any) -> Any:
        """Recursively substitute environment variables in configuration data.
        
        Supports the following formats:
        - ${VAR_NAME} - Required environment variable
        - ${VAR_NAME:default_value} - Optional with default value
        """
        if isinstance(data, dict):
            return {key: self._substitute_environment_variables(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._substitute_environment_variables(item) for item in data]
        elif isinstance(data, str):
            return self._substitute_env_vars_in_string(data)
        else:
            return data

    def _substitute_env_vars_in_string(self, text: str) -> str:
        """Substitute environment variables in a string."""
        # Pattern to match ${VAR_NAME} or ${VAR_NAME:default_value}
        pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'
        
        def replace_var(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else None
            
            env_value = os.getenv(var_name)
            
            if env_value is not None:
                return env_value
            elif default_value is not None:
                return default_value
            else:
                raise ValueError(f"Required environment variable '{var_name}' is not set")
        
        return re.sub(pattern, replace_var, text)

    def load_config(self, config_path: str) -> Config:
        """Load configuration from YAML file with environment variable substitution."""
        try:
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"Configuration file not found: {config_path}")

            if not os.access(config_path, os.R_OK):
                raise PermissionError(f"Cannot read configuration file: {config_path}")

            with open(config_path, "r", encoding="utf-8") as file:
                try:
                    raw_config_data = yaml.safe_load(file)
                except yaml.YAMLError as e:
                    raise ValueError(f"Invalid YAML syntax in configuration file: {e}")

            if raw_config_data is None:
                raise ValueError("Configuration file is empty or contains only comments")

            if not isinstance(raw_config_data, dict):
                raise ValueError("Configuration file must contain a YAML dictionary at the root level")

            # Substitute environment variables
            try:
                config_data = self._substitute_environment_variables(raw_config_data)
            except ValueError as e:
                raise ValueError(f"Environment variable substitution failed: {e}")

        except (FileNotFoundError, PermissionError, ValueError) as e:
            raise e
        except Exception as e:
            raise RuntimeError(f"Unexpected error loading configuration file '{config_path}': {e}")

        try:
            # Parse OpenStack credentials
            openstack_config = config_data.get("openstack", {})
            if not openstack_config:
                raise ValueError("Missing required 'openstack' configuration section")

            auth_method_str = openstack_config.get("auth_method", "application_credential")
            try:
                auth_method = AuthMethod(auth_method_str)
            except ValueError:
                raise ValueError(f"Invalid auth_method '{auth_method_str}'. Must be 'application_credential' or 'password'")

            openstack_creds = OpenStackCredentials(
                auth_method=auth_method,
                auth_url=openstack_config.get("auth_url"),
                project_name=openstack_config.get("project_name"),
                application_credential_id=openstack_config.get("application_credential_id"),
                application_credential_secret=openstack_config.get(
                    "application_credential_secret"
                ),
                username=openstack_config.get("username"),
                password=openstack_config.get("password"),
                user_domain_name=openstack_config.get("user_domain_name", "Default"),
                project_domain_name=openstack_config.get("project_domain_name", "Default"),
            )

            # Parse backup configuration
            backup_config_data = config_data.get("backup", {})
            backup_config = BackupConfig(
                full_backup_interval_days=int(backup_config_data.get(
                    "full_backup_interval_days", 7
                )),
                max_concurrent_operations=int(backup_config_data.get(
                    "max_concurrent_operations", 5
                )),
                operation_timeout_minutes=int(backup_config_data.get(
                    "operation_timeout_minutes", 60
                )),
                # Support both new and legacy config formats
                snapshot_retention_days=int(backup_config_data.get("snapshot_retention_days", 
                    backup_config_data.get("retention_days", 7))),
                backup_retention_days=int(backup_config_data.get("backup_retention_days", 
                    backup_config_data.get("retention_days", 30))),
                default_retention_days=int(backup_config_data.get("retention_days", 30)),
            )

            # Parse email settings
            email_config = config_data.get("notifications", {})
            if not email_config:
                raise ValueError("Missing required 'notifications' configuration section")

            email_settings = EmailSettings(
                recipient=email_config.get("email_recipient"),
                sender=email_config.get("email_sender"),
                smtp_server=email_config.get("smtp_server", "localhost"),
                smtp_port=int(email_config.get("smtp_port", 25)),
                use_tls=bool(email_config.get("use_tls", False)),
                username=email_config.get("smtp_username"),
                password=email_config.get("smtp_password"),
            )

            # Parse scheduling configuration
            scheduling_config_data = config_data.get("scheduling", {})
            mode_str = scheduling_config_data.get("mode", "cron")
            try:
                mode = SchedulingMode(mode_str)
            except ValueError:
                raise ValueError(
                    f"Invalid scheduling mode: {mode_str}. Must be 'cron' or 'daemon'"
                )

            scheduling_config = SchedulingConfig(
                mode=mode,
                check_interval_minutes=int(scheduling_config_data.get(
                    "check_interval_minutes", 15
                )),
                daemon_sleep_seconds=int(scheduling_config_data.get("daemon_sleep_seconds", 60)),
            )

            # Parse retention policies
            retention_policies = {}
            retention_config = config_data.get("retention_policies", {})
            for name, policy_data in retention_config.items():
                if not isinstance(policy_data, dict):
                    raise ValueError(f"Retention policy '{name}' must be a dictionary")
                
                retention_policies[name] = RetentionPolicy(
                    retention_days=int(policy_data.get(
                        "retention_days", backup_config.default_retention_days
                    )),
                    min_backups_to_keep=int(policy_data.get("min_backups_to_keep", 1)),
                    keep_last_full_backup=bool(policy_data.get("keep_last_full_backup", True)),
                )

            # Create main config object
            self._config = Config(
                openstack=openstack_creds,
                backup=backup_config,
                notifications=email_settings,
                scheduling=scheduling_config,
                retention_policies=retention_policies,
                database_path=config_data.get(
                    "database_path", "./backup.db"
                ),
                log_level=config_data.get("log_level", "INFO"),
                log_file=config_data.get("log_file"),
            )

            # Configuration validation is handled automatically by dataclass __post_init__ methods
            return self._config

        except ValueError as e:
            # Re-raise ValueError with context
            raise ValueError(f"Configuration validation failed: {e}")
        except Exception as e:
            # Catch any other exceptions during parsing
            raise RuntimeError(f"Unexpected error parsing configuration: {e}")

    def get_openstack_credentials(self) -> OpenStackCredentials:
        """Get OpenStack authentication credentials."""
        if not self._config:
            raise RuntimeError("Configuration not loaded")
        return self._config.openstack

    def get_email_settings(self) -> EmailSettings:
        """Get email notification settings."""
        if not self._config:
            raise RuntimeError("Configuration not loaded")
        return self._config.notifications

    def get_retention_policies(self) -> Dict[str, RetentionPolicy]:
        """Get retention policies configuration."""
        if not self._config:
            raise RuntimeError("Configuration not loaded")
        return self._config.retention_policies

    def validate_config(self, config: Config) -> bool:
        """Validate configuration completeness and correctness.

        Note: Most validation is now handled automatically by dataclass __post_init__ methods.
        This method is kept for backward compatibility and additional cross-field validation.
        """
        # Additional cross-field validation can be added here if needed
        # For now, individual dataclass validation is sufficient
        return True
