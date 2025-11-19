# OpenStack Backup Automation

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Automated backup and snapshot system for OpenStack resources based on tags.

## Quick Start (Repository-based)

### 1. Clone and Setup
```bash
git clone <repository-url> openstack-backup-automation
cd openstack-backup-automation
```

### 2. Install Dependencies
```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install the backup automation package
pip install -e .
```

### 3. Configure
```bash
# Copy example configuration
cp config.yaml.example config.yaml

# Edit with your OpenStack credentials and timezone
vi config.yaml
```

**Important:** Set the `timezone` in config.yaml to match your local timezone. Schedule times in tags (e.g., `SNAPSHOT-DAILY-0300`) are interpreted in this timezone.

```yaml
# config.yaml
timezone: "Europe/Berlin"  # or "UTC", "America/New_York", etc.
```

### 4. Test Configuration
```bash
# Validate configuration
openstack-backup-automation config-validate

# Test run (dry-run)
openstack-backup-automation run --dry-run
```

### 5. Setup Automatic Execution
```bash
# Setup cron job (runs every 15 minutes by default unless otherwise configured)
./scripts/setup-cron.sh

# Or with custom interval
./scripts/setup-cron.sh --interval 30
```

## Tag Your Resources

### Instance Tags
```bash
# Daily snapshots at 03:00 (instance and volumes)
openstack server set --tag "SNAPSHOT-DAILY-0300" my-web-server

# Weekly backups on Monday at 02:00 (all attached volumes)
openstack server set --tag "BACKUP-WEEKLY-0200" my-database-server

# Monthly backups on 1st at 01:00 (all attached volumes)
openstack server set --tag "BACKUP-MONTHLY-0100" my-storage-server
```

### Volume Metadata (for individual volume backups)
```bash
# Daily volume backups at 04:00, keep 60 days
openstack volume set --property backup="BACKUP-DAILY-0400-RETAIN60" my-important-volume

# Weekly volume backups on Sunday at 01:00
openstack volume set --property backup="BACKUP-SUNDAY-0100" my-data-volume

# Weekly volume snapshot on Wednesday at 02:30, keep 14 days
openstack volume set --property backup="SNAPSHOT-WEDNESDAY-0230-RETAIN14" my-volume

# Note: Volumes use metadata with key "backup" (not tags)
# If you tag an instance with BACKUP-*, all attached volumes 
# are automatically included. Individual volume metadata is only needed
# for standalone volumes or different schedules.
```

## Tag Behavior

### Instance Tags
- **SNAPSHOT-*** tags: Create instance snapshots and volume snapshots of all attached volumes (fast, instance-level backup)
- **BACKUP-*** tags: Create volume backups of all attached volumes (comprehensive backup)

### Volume Tags  
- **SNAPSHOT-*** tags: Create volume snapshots
- **BACKUP-*** tags: Create volume backups (full/incremental)

### Automatic Volume Inclusion
When you tag an instance with a **BACKUP-*** tag, the system automatically:
1. Discovers all volumes attached to that instance  
2. Creates volume backups for each attached volume with the same schedule
3. Uses the same retention policy for all components

This provides a simple "one-tag backup solution" for complete server protection.

## Tag Format

### Basic Format
```
{TYPE}-{FREQUENCY}-{TIME}

TYPE: SNAPSHOT | BACKUP
FREQUENCY: DAILY | WEEKLY | MONTHLY | MONDAY | TUESDAY | WEDNESDAY | THURSDAY | FRIDAY | SATURDAY | SUNDAY
TIME: HHMM (24-hour format)
```

### Extended Format (with retention and full backup interval)
```
{TYPE}-{FREQUENCY}-{TIME}-RETAIN{DAYS}
{TYPE}-{FREQUENCY}-{TIME}-FULL{DAYS}
{TYPE}-{FREQUENCY}-{TIME}-RETAIN{DAYS}-FULL{DAYS}

Examples:
BACKUP-DAILY-0300-RETAIN60        # Daily backups, keep 60 days
BACKUP-DAILY-0200-FULL7           # Daily backups, full backup every 7 days
BACKUP-DAILY-0300-RETAIN90-FULL14 # Daily backups, keep 90 days, full every 14 days
```

## Configuration

Edit `config.yaml` with your settings:

```yaml
openstack:
  auth_method: "application_credential"
  auth_url: "https://your-openstack.example.com:5000/v3"
  project_name: "your-project"
  application_credential_id: "your-app-cred-id"
  application_credential_secret: "your-app-cred-secret"

backup:
  full_backup_interval_days: 7
  max_concurrent_operations: 5
  operation_timeout_minutes: 60

notifications:
  enabled: false  # Set to true to enable email notifications
  email_recipient: "admin@example.com"
  email_sender: "backup-system@example.com"

retention_policies:
  default:
    retention_days: 30
    keep_last_full_backup: true
  snapshots:
    retention_days: 7
```

## Manual Execution

```bash
# Validate configuration
openstack-backup-automation config-validate

# Dry run (test mode - shows what would be done)
openstack-backup-automation run --dry-run

# Run backup cycle
openstack-backup-automation run

# Check system health
openstack-backup-automation health
```

### Manual Testing

#### Test Mode for Development
```bash
# Test mode - ignore timing, execute all policies
openstack-backup-automation run --test-mode

# Test mode with dry run - safe testing without creating actual backups
openstack-backup-automation run --test-mode --dry-run

# Normal dry run - respect timing, simulate operations
openstack-backup-automation run --dry-run
```

#### Database Inspection
```bash
# Check database contents
sqlite3 backup.db "SELECT backup_id, resource_id, backup_type, created_at FROM backups ORDER BY created_at;"

# Clean up cache files
./scripts/cleanup_cache.sh
```

## Monitoring

```bash
# View cron jobs
crontab -l

# Monitor cron execution
tail -f /var/log/syslog | grep CRON

# Check backup logs
tail -f logs/backup.log
```

## Remove Cron Job

```bash
./scripts/setup-cron.sh --remove
```

## Backup Strategy

The system implements a **defensive backup strategy** for immediate protection of new resources:

### Immediate Backup on Tag Addition

When you add a backup tag to a resource, the system does **not** wait until the next scheduled time:

```bash
# Example: Tag added at 10:30 AM
openstack server set --tag "BACKUP-DAILY-0300" my-server

# ✅ 10:45 AM: Immediate full backup on next scan (every 15 min)
# ✅ 03:00 AM (next day): Regular incremental backup
# ✅ 03:00 AM (following days): Continued daily backups
```

### Schedule After First Backup

After the first defensive backup, the system follows the normal schedule:

- **Daily Backups**: Incremental backups every 24 hours at configured time
- **Full Backup Interval**: Default every 7 days (configurable)
- **Retention**: Automatic cleanup after configured days

### Benefits

- **Immediate Protection**: Maximum 15 minutes wait time after tag addition
- **No Data Loss Risk**: Resources are protected immediately
- **Seamless Integration**: Normal schedule from second backup onwards

## Features

- ✅ Tag-based resource discovery
- ✅ **Defensive backup strategy** (immediate protection)
- ✅ Automated snapshots and backups
- ✅ Full/Incremental backup strategies
- ✅ Configurable retention policies
- ✅ Parallel operation execution
- ✅ Email notifications on errors
- ✅ Cron integration
- ✅ Comprehensive logging
- ✅ Health monitoring

## Advanced Features

For detailed information about advanced retention management features including batch deletion, policy priorities, and backup chain integrity, see [docs/retention-management.md](docs/retention-management.md).

# Roadmap
## Advanced Features

For information about planned and ongoing development, see [ROADMAP.md](ROADMAP.md).

## Development

### Running Tests Locally
```bash
# Install development dependencies (includes testing and linting tools)
pip install -r requirements-dev.txt

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_tag_scanner.py -v

# Pre-Push Check (lint code, check syntax, execute tests)
./scripts/pre-push-check.sh
```

### Continuous Integration
This project uses GitHub Actions for automated testing:
- **Tests**: Run on Python 3.8-3.12
- **Linting**: Code style and import sorting checks
- **Config Validation**: Ensures example configuration is valid

## Troubleshooting

### Debug Mode

Enable detailed logging for troubleshooting:

```yaml
# config.yaml
logging:
  level: "DEBUG"  # Change from INFO to DEBUG
  console_enabled: true
  file_logging: true
```

Then check logs:
```bash
# View logs
tail -f logs/backup-automation.log

# Filter for errors
grep ERROR logs/backup-automation.log

# Check specific resource
grep "resource-id" logs/backup-automation.log
```

### Getting Help

If you encounter issues:

1. **Check logs** for error messages
2. **Validate configuration** with `config-validate` command
3. **Test connectivity** to OpenStack APIs
4. **Review permissions** for files and directories
5. **Check resource tags** are properly formatted
6. **Verify timing** with `--dry-run` mode

For additional support, check the project documentation or open an issue on GitHub.

## Requirements

- Python 3.8+
- Valid OpenStack credentials
- SMTP access for notifications (optional)

## License

MIT License
