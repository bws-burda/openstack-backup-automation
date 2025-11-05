"""Command-line interface for OpenStack Backup Automation."""

import asyncio
import logging
import os
import shutil
import sys
from typing import Optional

import click

from ..config.manager import ConfigurationManager
from ..factory import create_coordinator_from_config
from ..logging.config import LoggingConfig
from ..logging.config import setup_logging as setup_comprehensive_logging
from ..scheduler.daemon import DaemonRunner


def setup_logging(log_level: str = "INFO", config_path: Optional[str] = None):
    """Configure logging with appropriate level and format."""
    if config_path and os.path.exists(config_path):
        try:
            # Load logging configuration from config file
            config_manager = ConfigurationManager()
            config = config_manager.load_config(config_path)
            logging_config = LoggingConfig(
                level=config.log_level,
                format_type=config.log_format,
                log_file=config.log_file,
                max_file_size_mb=config.log_max_size_mb,
                backup_count=config.log_backup_count,
                console_enabled=config.log_console_enabled,
                syslog_enabled=config.log_syslog_enabled,
            )
            setup_comprehensive_logging(logging_config)
            return
        except Exception:
            # Fall back to basic logging if config loading fails
            pass
    # Basic logging setup as fallback
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


@click.group()
@click.option(
    "--config",
    "-c",
    default="./config.yaml",
    help="Path to configuration file (default: ./config.yaml)",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Set logging level",
)
@click.pass_context
def cli(ctx, config, log_level):
    """OpenStack Backup Automation - Automated backup and snapshot system for OpenStack resources.
    This tool automatically creates backups and snapshots of OpenStack instances and volumes
    based on schedule tags. It supports both cron-based and daemon execution modes.
    Examples:
        # Run a single backup cycle (cron mode)
        openstack-backup-automation run
        # Run as daemon with continuous monitoring
        openstack-backup-automation run --daemon
        # Validate configuration file
        openstack-backup-automation config-validate
        # Install systemd service
        sudo openstack-backup-automation install --systemd
    """
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["log_level"] = log_level
    setup_logging(log_level, config)


@cli.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without executing operations",
)
@click.option("--daemon", is_flag=True, help="Run as daemon with continuous monitoring")
@click.option("--status", is_flag=True, help="Show current system status and exit")
@click.pass_context
def run(ctx, dry_run, daemon, status):
    """Execute backup operations.
    This command runs the backup automation system. By default, it performs
    a single backup cycle (suitable for cron execution). Use --daemon for
    continuous operation.
    Examples:
        # Single backup cycle (cron mode)
        openstack-backup-automation run
        # Dry run to see what would be done
        openstack-backup-automation run --dry-run
        # Run as daemon
        openstack-backup-automation run --daemon
        # Check system status
        openstack-backup-automation run --status
    """
    config_path = ctx.obj["config"]
    if not os.path.exists(config_path):
        click.echo(f"Error: Configuration file not found: {config_path}", err=True)
        click.echo(
            "Copy config.yaml.example to config.yaml and adjust the values for your environment."
        )
        sys.exit(1)
    try:
        # Create coordinator
        coordinator = create_coordinator_from_config(config_path)
        if status:
            # Show status
            async def show_status():
                info = await coordinator.get_system_status()
                click.echo("=== OpenStack Backup Automation Status ===")
                click.echo(f"Configuration: {config_path}")
                click.echo(f"Scheduled resources: {info['total_scheduled_resources']}")
                click.echo(
                    f"Resources due for backup: {info['resources_due_for_backup']}"
                )
                click.echo(f"Last backup time: {info['last_backup_time'] or 'Never'}")
                click.echo(
                    f"System status: {'Healthy' if info['healthy'] else 'Issues detected'}"
                )

            asyncio.run(show_status())
        elif daemon:
            # Run daemon mode
            config_manager = ConfigurationManager()
            config_obj = config_manager.load_config(config_path)
            runner = DaemonRunner(
                coordinator, config_obj.scheduling.check_interval_minutes
            )
            click.echo(
                f"Starting daemon mode (checking every {config_obj.scheduling.check_interval_minutes} minutes)"
            )
            click.echo("Press Ctrl+C to stop")
            sys.exit(runner.run_sync())
        else:
            # Run single backup cycle (cron mode)
            async def run_backup():
                if dry_run:
                    click.echo("=== DRY RUN MODE - No operations will be executed ===")
                results = await coordinator.execute_backup_cycle(dry_run=dry_run)
                click.echo("Backup cycle completed:")
                click.echo(f"  Operations executed: {results['operations_executed']}")
                click.echo(f"  Successful: {results['successful_operations']}")
                click.echo(f"  Failed: {len(results['errors'])}")
                if results["errors"]:
                    click.echo("\nErrors encountered:")
                    for error in results["errors"]:
                        click.echo(f"  - {error}", err=True)
                    sys.exit(1)
                else:
                    click.echo("All operations completed successfully.")

            asyncio.run(run_backup())
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--json", "output_json", is_flag=True, help="Output status in JSON format"
)
@click.option(
    "--component",
    help="Check specific component (database, openstack_api, local_storage, openstack_quotas)",
)
@click.option("--export", help="Export status report to file")
@click.pass_context
def health(ctx, output_json, component, export):
    """Check system health and component status.
    This command performs health checks on system components including
    database connectivity, OpenStack API access, and disk space.
    Examples:
        # Check overall system health
        openstack-backup-automation health
        # Check specific component
        openstack-backup-automation health --component database
        # Export status to JSON file
        openstack-backup-automation health --export status.json
        # Get JSON output for monitoring systems
        openstack-backup-automation health --json
    """
    config_path = ctx.obj["config"]
    if not os.path.exists(config_path):
        click.echo(f"Error: Configuration file not found: {config_path}", err=True)
        sys.exit(1)
    try:
        from ..factory import (
            create_health_checker_from_config,
            create_status_reporter_from_config,
        )

        async def check_health():
            health_checker = create_health_checker_from_config(config_path)
            status_reporter = create_status_reporter_from_config(config_path)
            if component:
                # Check specific component
                component_health = await health_checker.check_component_health(
                    component
                )
                if not component_health:
                    click.echo(f"Error: Unknown component '{component}'", err=True)
                    sys.exit(1)
                if output_json:
                    import json

                    result = {
                        "component": component_health.name,
                        "status": component_health.status.value,
                        "message": component_health.message,
                        "last_check": component_health.last_check.isoformat(),
                        "details": component_health.details,
                    }
                    click.echo(json.dumps(result, indent=2))
                else:
                    status_symbol = (
                        "✓"
                        if component_health.is_healthy()
                        else "⚠" if component_health.is_degraded() else "✗"
                    )
                    click.echo(
                        f"{status_symbol} {component_health.name}: {component_health.status.value}"
                    )
                    click.echo(f"  Message: {component_health.message}")
                    if component_health.details:
                        click.echo(f"  Details: {component_health.details}")
            else:
                # Check overall system health
                system_status = await health_checker.check_system_health()
                if export:
                    # Export to file
                    success = status_reporter.export_status_json(system_status, export)
                    if success:
                        click.echo(f"✓ Status exported to {export}")
                    else:
                        click.echo(f"✗ Failed to export status to {export}", err=True)
                        sys.exit(1)
                if output_json:
                    click.echo(json.dumps(system_status.to_dict(), indent=2))
                else:
                    # Human-readable output
                    overall_symbol = (
                        "✓"
                        if system_status.overall_status.value == "healthy"
                        else (
                            "⚠"
                            if system_status.overall_status.value == "degraded"
                            else "✗"
                        )
                    )
                    click.echo("=== System Health Status ===")
                    click.echo(
                        f"{overall_symbol} Overall Status: {system_status.overall_status.value.upper()}"
                    )
                    if system_status.uptime_seconds:
                        uptime_hours = system_status.uptime_seconds / 3600
                        click.echo(f"Uptime: {uptime_hours:.1f} hours")
                    click.echo(f"Timestamp: {system_status.timestamp.isoformat()}")
                    click.echo("")
                    click.echo("Component Status:")
                    for comp in system_status.components:
                        comp_symbol = (
                            "✓"
                            if comp.is_healthy()
                            else "⚠" if comp.is_degraded() else "✗"
                        )
                        click.echo(
                            f"  {comp_symbol} {comp.name}: {comp.status.value} - {comp.message}"
                        )
                    # Show recommendations if any
                    report = status_reporter.generate_health_report(system_status)
                    if report.get("recommendations"):
                        click.echo("")
                        click.echo("Recommendations:")
                        for i, rec in enumerate(report["recommendations"], 1):
                            click.echo(f"  {i}. {rec}")
                # Send alert if system is unhealthy
                if system_status.has_critical_issues():
                    status_reporter.send_health_alert(system_status)
                    sys.exit(1)

        asyncio.run(check_health())
    except Exception as e:
        click.echo(f"Health check failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--create-example", is_flag=True, help="Create an example configuration file"
)
@click.option(
    "--output",
    "-o",
    default="config.yaml",
    help="Output file for example configuration (default: config.yaml)",
)
@click.pass_context
def config_validate(ctx, create_example, output):
    """Validate configuration file or create example configuration.
    This command validates the syntax and content of your configuration file.
    It checks for required fields, valid values, and OpenStack connectivity.
    Examples:
        # Validate current configuration
        openstack-backup-automation config-validate
        # Create example configuration
        openstack-backup-automation config-validate --create-example
        # Create example with custom filename
        openstack-backup-automation config-validate --create-example -o my-config.yaml
    """
    config_path = ctx.obj["config"]
    if create_example:
        example_config = """# OpenStack Backup Automation Configuration
# This is an example configuration file. Adjust values according to your environment.
openstack:
  # Authentication method: "application_credential" (recommended) or "password"
  auth_method: "application_credential"
  # Application Credential authentication (recommended)
  application_credential_id: "your-app-credential-id"
  application_credential_secret: "your-app-credential-secret"
  # Alternative: Username/Password authentication
  # username: "your-username"
  # password: "your-password"
  # user_domain_name: "Default"
  # OpenStack endpoints
  auth_url: "https://your-openstack.example.com:5000/v3"
  project_name: "your-project-name"
  project_domain_name: "Default"
  region_name: "RegionOne"
backup:
  # Full backup interval (days between full backups)
  full_backup_interval_days: 7
  # Retention period for backups (days)
  retention_days: 30
  # Maximum concurrent backup/snapshot operations
  max_concurrent_operations: 5
  # Timeout for individual operations (minutes)
  operation_timeout_minutes: 60
notifications:
  # Email settings for error notifications
  email_recipient: "admin@example.com"
  email_sender: "backup-system@example.com"
  # Optional: SMTP settings (uses local sendmail if not specified)
  # smtp_server: "smtp.example.com"
  # smtp_port: 587
  # smtp_username: "smtp-user"
  # smtp_password: "smtp-password"
  # smtp_use_tls: true
scheduling:
  # Execution mode: "cron" (default) or "daemon"
  mode: "cron"
  # Check interval for daemon mode (minutes)
  check_interval_minutes: 15
# Logging configuration
logging:
  # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_level: "INFO"
  # Log format: "structured" (JSON), "simple", or "detailed"
  log_format: "structured"
  # Optional: Log to file with rotation
  # log_file: "/var/log/backup-automation/backup.log"
  # log_max_size_mb: 10
  # log_backup_count: 5
  # Console and syslog options
  log_console_enabled: true
  log_syslog_enabled: false
# Monitoring and health checks
monitoring:
  enabled: true
  check_interval_seconds: 60
  timeout_seconds: 30
  # Component-specific checks
  database_check_enabled: true
  openstack_check_enabled: true
  local_storage_check_enabled: true
  local_storage_threshold_percent: 95  # High threshold - only for metadata
  openstack_quota_check_enabled: true
  # Status reporting
  status_report_enabled: false
  status_report_interval_hours: 24
# Optional: Custom retention policies per resource type
# retention_policies:
#   instances:
#     retention_days: 14
#   volumes:
#     retention_days: 30
"""
        if os.path.exists(output) and not click.confirm(
            f"File {output} already exists. Overwrite?"
        ):
            click.echo("Operation cancelled.")
            return
        with open(output, "w") as f:
            f.write(example_config)
        click.echo(f"✓ Example configuration created: {output}")
        click.echo("Please edit the file with your OpenStack credentials and settings.")
        return
    if not os.path.exists(config_path):
        click.echo(f"Error: Configuration file not found: {config_path}", err=True)
        click.echo("Copy config.yaml.example to config.yaml and adjust the values.")
        sys.exit(1)
    try:
        config_manager = ConfigurationManager()
        config_obj = config_manager.load_config(config_path)
        click.echo("✓ Configuration file syntax is valid")
        # Test OpenStack connectivity
        click.echo("Testing OpenStack connectivity...")
        from ..openstack_api.client import OpenStackClient

        async def test_connection():
            client = OpenStackClient()
            try:
                auth_success = client.authenticate(config_obj.openstack)
                if not auth_success:
                    click.echo("✗ OpenStack authentication failed", err=True)
                    return False
                click.echo("✓ OpenStack authentication successful")
                # Test basic API access with minimal permissions
                if client.connection:
                    # Simple test - list servers (compute access, which backup needs anyway)
                    try:
                        list(client.connection.compute.servers(limit=1))
                        click.echo("✓ OpenStack API access verified")
                    except Exception as e:
                        # If compute access fails, try a different service
                        try:
                            list(client.connection.volume.volumes(limit=1))
                            click.echo(
                                "✓ OpenStack API access verified (via volume service)"
                            )
                        except Exception:
                            click.echo(
                                f"⚠ Limited API access - some services may not be available: {e}",
                                err=True,
                            )
                            click.echo(
                                "✓ Basic authentication works, but check service permissions"
                            )
                else:
                    click.echo("✗ No OpenStack connection established", err=True)
                    return False
            except Exception as e:
                click.echo(f"✗ OpenStack connection failed: {e}", err=True)
                return False
            finally:
                # Clean up connection if it exists
                if hasattr(client, "connection") and client.connection:
                    client.connection.close()
            return True

        success = asyncio.run(test_connection())
        if success:
            click.echo("✓ Configuration is valid and OpenStack is accessible")
        else:
            click.echo(
                "Configuration file is valid but OpenStack connection failed", err=True
            )
            sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Configuration validation failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--systemd", is_flag=True, help="Install systemd service and timer")
@click.option("--cron", is_flag=True, help="Install cron job")
@click.option(
    "--user", default="backup", help="System user for the service (default: backup)"
)
@click.option(
    "--config-dir",
    default="/etc/backup-automation",
    help="Configuration directory (default: /etc/backup-automation)",
)
@click.option(
    "--data-dir",
    default="/var/lib/backup-automation",
    help="Data directory for database and logs (default: /var/lib/backup-automation)",
)
@click.pass_context
def install(ctx, systemd, cron, user, config_dir, data_dir):
    """Install OpenStack Backup Automation as a system service.
    This command helps you install the backup automation system as either
    a systemd service or cron job. It creates necessary directories, users,
    and configuration files.
    Examples:
        # Install as systemd service (recommended)
        sudo openstack-backup-automation install --systemd
        # Install as cron job
        sudo openstack-backup-automation install --cron
        # Install with custom user and directories
        sudo openstack-backup-automation install --systemd --user mybackup --config-dir /opt/backup/config
    """
    if not systemd and not cron:
        click.echo("Error: Please specify either --systemd or --cron", err=True)
        sys.exit(1)
    if os.geteuid() != 0:
        click.echo(
            "Error: Installation requires root privileges. Please run with sudo.",
            err=True,
        )
        sys.exit(1)
    try:
        # Create system user if it doesn't exist
        import subprocess

        try:
            subprocess.run(["id", user], check=True, capture_output=True)
            click.echo(f"✓ User '{user}' already exists")
        except subprocess.CalledProcessError:
            subprocess.run(
                [
                    "useradd",
                    "--system",
                    "--shell",
                    "/bin/false",
                    "--home-dir",
                    data_dir,
                    "--create-home",
                    user,
                ],
                check=True,
            )
            click.echo(f"✓ Created system user '{user}'")
        # Create directories
        for directory in [config_dir, data_dir]:
            os.makedirs(directory, exist_ok=True)
            shutil.chown(directory, user, user)
            os.chmod(directory, 0o750)
            click.echo(f"✓ Created directory: {directory}")
        if systemd:
            install_systemd_service(user, config_dir, data_dir)
        if cron:
            install_cron_job(user, config_dir, data_dir)
        click.echo("\n✓ Installation completed successfully!")
        click.echo("Next steps:")
        click.echo(f"1. Copy your configuration to: {config_dir}/config.yaml")
        click.echo(
            f"2. Ensure the configuration is owned by {user}:root with 640 permissions"
        )
        if systemd:
            click.echo(
                "3. Enable and start the service: systemctl enable --now backup-automation.timer"
            )
        if cron:
            click.echo(
                "3. The cron job has been installed and will run every 15 minutes"
            )
    except Exception as e:
        click.echo(f"Installation failed: {e}", err=True)
        sys.exit(1)


def install_systemd_service(user, config_dir, data_dir):
    """Install systemd service and timer files."""
    service_content = f"""[Unit]
Description=OpenStack Backup Automation
Documentation=https://github.com/example/openstack-backup-automation
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User={user}
Group={user}
WorkingDirectory={data_dir}
Environment=CONFIG_FILE={config_dir}/config.yaml
ExecStart=/usr/local/bin/openstack-backup-automation run
StandardOutput=journal
StandardError=journal
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={data_dir}
ReadOnlyPaths={config_dir}
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
"""
    timer_content = """[Unit]
Description=Run OpenStack Backup Automation every 15 minutes
Documentation=https://github.com/example/openstack-backup-automation
Requires=backup-automation.service
[Timer]
OnCalendar=*:0/15
Persistent=true
RandomizedDelaySec=60
[Install]
WantedBy=timers.target
"""
    # Write service file
    service_path = "/etc/systemd/system/backup-automation.service"
    with open(service_path, "w") as f:
        f.write(service_content)
    os.chmod(service_path, 0o644)
    # Write timer file
    timer_path = "/etc/systemd/system/backup-automation.timer"
    with open(timer_path, "w") as f:
        f.write(timer_content)
    os.chmod(timer_path, 0o644)
    # Reload systemd
    import subprocess

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    click.echo("✓ Systemd service and timer installed")
    click.echo("  Service: backup-automation.service")
    click.echo("  Timer: backup-automation.timer")


def install_cron_job(user, config_dir, data_dir):
    """Install cron job for the specified user."""
    cron_file = "/etc/cron.d/backup-automation"
    with open(cron_file, "w") as f:
        f.write("# OpenStack Backup Automation\n")
        f.write(
            f"*/15 * * * * {user} cd {data_dir} && CONFIG_FILE={config_dir}/config.yaml /usr/local/bin/openstack-backup-automation run >/dev/null 2>&1\n"
        )
    os.chmod(cron_file, 0o644)
    click.echo("✓ Cron job installed: /etc/cron.d/backup-automation")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
