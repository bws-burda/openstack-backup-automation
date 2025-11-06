"""Simple factory for creating system components."""

from .backup.engine import BackupEngine
from .config.manager import ConfigurationManager
from .monitoring.health_checker import HealthChecker
from .monitoring.models import HealthCheckConfig
from .monitoring.status_reporter import StatusReporter
from .notification.service import NotificationService
from .openstack_api.client import OpenStackClient
from .retention.manager import RetentionManager
from .scanner.tag_scanner import TagScanner
from .scheduler.coordinator import ExecutionCoordinator
from .state.manager import StateManager


def create_coordinator_from_config(config_path: str) -> ExecutionCoordinator:
    """Create execution coordinator from configuration file."""
    # Load configuration
    config_manager = ConfigurationManager()
    config = config_manager.load_config(config_path)

    # Create OpenStack client and authenticate
    openstack_client = OpenStackClient()
    if not openstack_client.authenticate(config.openstack):
        raise RuntimeError("Failed to authenticate with OpenStack")

    # Create components
    state_manager = StateManager(config.database_path)
    tag_scanner = TagScanner(openstack_client)

    backup_engine = BackupEngine(
        openstack_client=openstack_client,
        state_manager=state_manager,
        max_concurrent_operations=config.backup.max_concurrent_operations,
        operation_timeout_minutes=config.backup.operation_timeout_minutes,
        full_backup_interval_days=config.backup.full_backup_interval_days,
    )

    retention_manager = RetentionManager(state_manager, openstack_client)

    # Create notification service (email is optional)
    notification_service = NotificationService(config.notifications)

    # Note: HealthChecker and StatusReporter are created on-demand by CLI commands

    # Create coordinator
    return ExecutionCoordinator(
        config=config,
        tag_scanner=tag_scanner,
        backup_engine=backup_engine,
        state_manager=state_manager,
        retention_manager=retention_manager,
        notification_service=notification_service,
    )


def create_health_checker_from_config(config_path: str) -> HealthChecker:
    """Create health checker from configuration file."""
    # Load configuration
    config_manager = ConfigurationManager()
    config = config_manager.load_config(config_path)

    # Create OpenStack client and authenticate
    openstack_client = OpenStackClient()
    if not openstack_client.authenticate(config.openstack):
        raise RuntimeError("Failed to authenticate with OpenStack")

    # Create state manager
    state_manager = StateManager(config.database_path)

    # Create health check configuration
    health_check_config = HealthCheckConfig(
        enabled=config.monitoring.enabled,
        check_interval_seconds=config.monitoring.check_interval_seconds,
        timeout_seconds=config.monitoring.timeout_seconds,
        database_check_enabled=config.monitoring.database_check_enabled,
        openstack_check_enabled=config.monitoring.openstack_check_enabled,
        local_storage_check_enabled=config.monitoring.local_storage_check_enabled,
        local_storage_threshold_percent=config.monitoring.local_storage_threshold_percent,
    )

    return HealthChecker(
        config=health_check_config,
        openstack_client=openstack_client,
        state_manager=state_manager,
        database_path=config.database_path,
    )


def create_status_reporter_from_config(config_path: str) -> StatusReporter:
    """Create status reporter from configuration file."""
    # Load configuration
    config_manager = ConfigurationManager()
    config = config_manager.load_config(config_path)

    # Create notification service and state manager (email is optional)
    notification_service = NotificationService(config.notifications)
    state_manager = StateManager(config.database_path)

    return StatusReporter(
        notification_service=notification_service,
        state_manager=state_manager,
    )
