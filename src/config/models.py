"""Configuration data models."""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class AuthMethod(Enum):
    """OpenStack authentication methods."""

    APPLICATION_CREDENTIAL = "application_credential"
    PASSWORD = "password"


@dataclass
class OpenStackCredentials:
    """OpenStack authentication credentials."""

    auth_method: AuthMethod
    auth_url: str
    project_name: str

    # Application Credential fields
    application_credential_id: Optional[str] = None
    application_credential_secret: Optional[str] = None

    # Username/Password fields
    username: Optional[str] = None
    password: Optional[str] = None
    user_domain_name: Optional[str] = "Default"
    project_domain_name: Optional[str] = "Default"

    # Optional fields
    region_name: Optional[str] = None

    def __post_init__(self):
        """Validate OpenStack credentials after initialization."""
        self._validate()

    def _validate(self):
        """Validate OpenStack credential configuration."""
        if not self.auth_url:
            raise ValueError("OpenStack auth_url is required")

        if not self.auth_url.startswith(("http://", "https://")):
            raise ValueError("OpenStack auth_url must be a valid HTTP/HTTPS URL")

        if not self.project_name:
            raise ValueError("OpenStack project_name is required")

        if self.auth_method == AuthMethod.APPLICATION_CREDENTIAL:
            if not self.application_credential_id:
                raise ValueError(
                    "Application credential ID is required for application credential auth"
                )
            if not self.application_credential_secret:
                raise ValueError(
                    "Application credential secret is required for application credential auth"
                )
        elif self.auth_method == AuthMethod.PASSWORD:
            if not self.username:
                raise ValueError("Username is required for password auth")
            if not self.password:
                raise ValueError("Password is required for password auth")
            if not self.user_domain_name:
                raise ValueError("User domain name is required for password auth")
            if not self.project_domain_name:
                raise ValueError("Project domain name is required for password auth")


@dataclass
class EmailSettings:
    """Email notification settings."""

    enabled: bool = False
    recipient: Optional[str] = None
    sender: Optional[str] = None
    smtp_server: str = "localhost"
    smtp_port: int = 25
    use_tls: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    send_reports: bool = True

    def __post_init__(self):
        """Validate email settings after initialization."""
        self._validate()

    def _validate(self):
        """Validate email configuration."""
        # Only validate email fields if notifications are enabled
        if not self.enabled:
            return

        if not self.recipient:
            raise ValueError(
                "Email recipient is required when notifications are enabled"
            )

        if not self.sender:
            raise ValueError("Email sender is required when notifications are enabled")

        # Basic email format validation
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, self.recipient):
            raise ValueError(f"Invalid email format for recipient: {self.recipient}")

        if not re.match(email_pattern, self.sender):
            raise ValueError(f"Invalid email format for sender: {self.sender}")

        # Validate SMTP port range
        if not (1 <= self.smtp_port <= 65535):
            raise ValueError(
                f"SMTP port must be between 1 and 65535, got: {self.smtp_port}"
            )

        # Validate SMTP server
        if not self.smtp_server:
            raise ValueError("SMTP server is required when notifications are enabled")

        # If TLS is enabled and port is default, suggest secure port
        if self.use_tls and self.smtp_port == 25:
            # This is just a warning, not an error
            pass


@dataclass
class RetentionPolicy:
    """Simplified backup retention policy configuration."""

    retention_days: int

    def __post_init__(self):
        """Validate retention policy after initialization."""
        self._validate()

    def _validate(self):
        """Validate retention policy configuration."""
        if self.retention_days <= 0:
            raise ValueError(
                f"Retention days must be positive, got: {self.retention_days}"
            )

        # Warn if retention is very short
        if self.retention_days < 7:
            # This is just a warning, not an error
            pass


@dataclass
class BackupConfig:
    """Backup operation configuration."""

    full_backup_interval_days: int = 7
    max_concurrent_operations: int = 5
    operation_timeout_minutes: int = 60

    def __post_init__(self):
        """Validate backup configuration after initialization."""
        self._validate()

    def _validate(self):
        """Validate backup configuration."""
        if self.full_backup_interval_days <= 0:
            raise ValueError(
                f"Full backup interval must be positive, got: {self.full_backup_interval_days}"
            )

        if self.max_concurrent_operations <= 0:
            raise ValueError(
                f"Max concurrent operations must be positive, got: {self.max_concurrent_operations}"
            )

        if self.max_concurrent_operations > 20:
            raise ValueError(
                f"Max concurrent operations should not exceed 20 to avoid API limits, got: {self.max_concurrent_operations}"
            )

        if self.operation_timeout_minutes <= 0:
            raise ValueError(
                f"Operation timeout must be positive, got: {self.operation_timeout_minutes}"
            )

        # Warn about very short full backup intervals
        if self.full_backup_interval_days < 3:
            # This is just a warning, not an error
            pass


@dataclass
class MonitoringConfig:
    """Monitoring and health check configuration."""

    timeout_seconds: int = 30
    local_storage_threshold_percent: int = 95

    def __post_init__(self):
        """Validate monitoring configuration after initialization."""
        self._validate()

    def _validate(self):
        """Validate monitoring configuration."""
        if self.timeout_seconds <= 0:
            raise ValueError(f"Timeout must be positive, got: {self.timeout_seconds}")

        if not (0 <= self.local_storage_threshold_percent <= 100):
            raise ValueError(
                f"Local storage threshold must be between 0 and 100, got: {self.local_storage_threshold_percent}"
            )


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    console_enabled: bool = True
    file_logging: bool = True
    log_file: str = "logs/backup-automation.log"
    max_file_size_mb: int = 100
    backup_count: int = 5


@dataclass
class Config:
    """Main configuration object."""

    openstack: OpenStackCredentials
    backup: BackupConfig
    notifications: EmailSettings
    retention_policies: Dict[str, RetentionPolicy] = field(default_factory=dict)

    # Database configuration
    database_path: str = "./backup.db"

    # Timezone for scheduling (e.g., "Europe/Berlin", "UTC", "America/New_York")
    timezone: str = "UTC"

    # Logging configuration
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Monitoring configuration
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)

    def __post_init__(self):
        """Validate main configuration after initialization."""
        self._validate()

    def _validate(self):
        """Validate main configuration."""
        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.logging.level.upper() not in valid_log_levels:
            raise ValueError(
                f"Invalid log level: {self.logging.level}. Must be one of: {valid_log_levels}"
            )

        # Normalize log level to uppercase
        self.logging.level = self.logging.level.upper()

        # Validate database path
        if not self.database_path:
            raise ValueError("Database path is required")

        # Check if database directory exists or can be created
        db_dir = os.path.dirname(self.database_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except (OSError, PermissionError) as e:
                raise ValueError(f"Cannot create database directory {db_dir}: {e}")

        # Validate log file path if specified
        if self.log_file:
            log_dir = os.path.dirname(self.log_file)
            if log_dir and not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except (OSError, PermissionError) as e:
                    raise ValueError(f"Cannot create log directory {log_dir}: {e}")

        # Validate retention policies
        if not isinstance(self.retention_policies, dict):
            raise ValueError("Retention policies must be a dictionary")

        # Validate each retention policy
        for name, policy in self.retention_policies.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    f"Retention policy name must be a non-empty string, got: {name}"
                )

            if not isinstance(policy, RetentionPolicy):
                raise ValueError(
                    f"Retention policy '{name}' must be a RetentionPolicy instance"
                )

    def get_retention_policy(self, policy_name: str) -> Optional[RetentionPolicy]:
        """Get a specific retention policy by name."""
        return self.retention_policies.get(policy_name)

    def add_retention_policy(self, name: str, policy: RetentionPolicy):
        """Add a new retention policy."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Policy name must be a non-empty string")

        if not isinstance(policy, RetentionPolicy):
            raise ValueError("Policy must be a RetentionPolicy instance")

        self.retention_policies[name] = policy

    # Backward compatibility properties for CLI
    @property
    def log_level(self) -> str:
        """Get log level (backward compatibility)."""
        return self.logging.level

    @property
    def log_file(self) -> Optional[str]:
        """Get log file (backward compatibility)."""
        return self.logging.log_file if self.logging.file_logging else None

    @property
    def log_max_size_mb(self) -> int:
        """Get log max size (backward compatibility)."""
        return self.logging.max_file_size_mb

    @property
    def log_backup_count(self) -> int:
        """Get log backup count (backward compatibility)."""
        return self.logging.backup_count

    @property
    def log_console_enabled(self) -> bool:
        """Get console enabled (backward compatibility)."""
        return self.logging.console_enabled
