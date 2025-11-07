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

# Edit with your OpenStack credentials
vi config.yaml
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
# Setup cron job (runs every 15 minutes)
./scripts/setup-cron.sh

# Or with custom interval
./scripts/setup-cron.sh --interval 30
```

## Tag Your Resources

### Instance Tags
```bash
# Daily snapshots at 03:00 (instance only)
openstack server set --tag "SNAPSHOT-DAILY-0300" my-web-server

# Weekly backups on Monday at 02:00 (instance + ALL attached volumes)
openstack server set --tag "BACKUP-WEEKLY-0200" my-database-server

# Monthly backups on 1st at 01:00 (instance + ALL attached volumes)
openstack server set --tag "BACKUP-MONTHLY-0100" my-storage-server
```

### Volume Metadata (for individual volume backups)
```bash
# Daily volume backups at 04:00, keep 60 days (single volume)
openstack volume set --property backup="BACKUP-DAILY-0400-RETAIN60" my-important-volume

# Weekly volume backups on Sunday at 01:00
openstack volume set --property backup="BACKUP-SUNDAY-0100" my-data-volume

# Note: Volumes use metadata with key "backup" (not tags)
# If you tag an instance with BACKUP-*, all attached volumes 
# are automatically included. Individual volume metadata is only needed
# for standalone volumes or different schedules.
```

## Tag Behavior

### Instance Tags
- **SNAPSHOT-*** tags: Create instance snapshots only (fast, instance-level backup)
- **BACKUP-*** tags: Create instance snapshot + backup ALL attached volumes (comprehensive backup)

### Volume Tags  
- **SNAPSHOT-*** tags: Create volume snapshots
- **BACKUP-*** tags: Create volume backups (full/incremental)

### Automatic Volume Inclusion
When you tag an instance with a **BACKUP-*** tag, the system automatically:
1. Creates an instance snapshot
2. Discovers all volumes attached to that instance  
3. Creates volume backups for each attached volume with the same schedule
4. Uses the same retention policy for all components

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

## Testing and Debugging

### Run Unit Tests
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_tag_scanner.py -v
```

### Manual Testing

#### Test Mode for Development
```bash
# Test mode - ignore timing, execute all policies (for testing backup chains)
openstack-backup-automation run --test-mode

# Test mode with dry run - safe testing without creating actual backups
openstack-backup-automation run --test-mode --dry-run

# Normal dry run - respect timing, simulate operations
openstack-backup-automation run --dry-run

# Test backup chains by running multiple times
openstack-backup-automation run --test-mode  # Run 1: Creates backups
openstack-backup-automation run --test-mode  # Run 2: Tests incremental logic
openstack-backup-automation run --test-mode  # Run 3: Tests full backup after interval
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

## System Installation (Alternative)

For system-wide installation:

```bash
sudo ./scripts/install.sh
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

## Development

### Running Tests Locally
```bash
# Install development dependencies (includes testing and linting tools)
pip install -r requirements-dev.txt

# Run all tests
python -m pytest tests/ -v
```

### Code Quality & Pre-Push Checks

**Run all checks before pushing (same as CI):**

```bash
# 1. Critical syntax errors (must pass)
flake8 src --count --select=E9,F63,F7,F82 --show-source --statistics

# 2. Code style warnings (informational, uses .flake8 config)
flake8 src --count --exit-zero --statistics

# 3. Code formatting check
black --check --diff src/

# 4. Import sorting check  
isort --check-only --diff src/

# 5. Configuration validation
python -c "
from src.config.manager import ConfigurationManager
import tempfile, shutil
shutil.copy('config.yaml.example', 'test-config.yaml')
try:
    manager = ConfigurationManager()
    config = manager.load_config('test-config.yaml')
    print('✅ Configuration file syntax is valid')
except Exception as e:
    if 'OpenStack' in str(e) or 'connection' in str(e).lower():
        print('✅ Configuration syntax valid (OpenStack connection expected to fail)')
    else:
        raise e
finally:
    import os
    if os.path.exists('test-config.yaml'):
        os.remove('test-config.yaml')
"
```

**Auto-fix formatting issues:**
```bash
# Fix code formatting
black src/

# Fix import sorting
isort src/
```

**One-command pre-push validation:**
```bash
# Run all checks at once (same as GitHub Actions)
./scripts/pre-push-checks.sh
```

### Continuous Integration
This project uses GitHub Actions for automated testing:
- **Tests**: Run on Python 3.8-3.12 across multiple OS
- **Linting**: Code style and import sorting checks  
- **Config Validation**: Ensures example configuration is valid

## Real-World Usage Examples

### Scenario 1: Production Database with Compliance Requirements
```bash
# Daily backups at 2 AM, keep for 1 year, full backup every 7 days
openstack server set --tag "BACKUP-DAILY-0200-RETAIN365-FULL7" prod-database-server

# Result: Complete server + all volumes backed up daily
# - Full backup every 7 days
# - Incremental backups on other days
# - Retention: 365 days
```

### Scenario 2: Development Environment with Cost Optimization
```bash
# Weekly snapshots on Sunday at 1 AM, keep only 2 weeks
openstack server set --tag "SNAPSHOT-SUNDAY-0100-RETAIN14" dev-environment

# Result: Fast snapshots, minimal storage cost
# - Only runs once per week
# - Short retention saves space
# - Quick restore capability
```

### Scenario 3: Mixed Backup Strategy for Web Application
```bash
# Web servers: Daily snapshots (fast recovery)
openstack server set --tag "SNAPSHOT-DAILY-0300-RETAIN30" web-server-01
openstack server set --tag "SNAPSHOT-DAILY-0300-RETAIN30" web-server-02

# Database server: Daily backups (data integrity)
openstack server set --tag "BACKUP-DAILY-0200-RETAIN90-FULL7" database-server

# File storage: Weekly backups (large data, less frequent changes)
openstack volume set --property backup="BACKUP-SATURDAY-0000-RETAIN180-FULL1" file-storage-volume

# Result: Optimized strategy per component
# - Web servers: Fast recovery with snapshots
# - Database: Comprehensive backups with incrementals
# - Storage: Weekly full backups for large data
```

### Scenario 4: Selective Volume Backup
```bash
# Instance with multiple volumes, only backup specific volumes
# Instance: NO TAG (not backed up)
# Root disk: NO TAG (not backed up)
# Data disk 1: Snapshot daily
openstack volume set --property backup="SNAPSHOT-DAILY-0300" data-disk-1-id

# Data disk 2: Full backup daily
openstack volume set --property backup="BACKUP-DAILY-0400-RETAIN60" data-disk-2-id

# Result: Granular control over what gets backed up
# - Only critical data volumes are backed up
# - Different strategies per volume
# - Cost optimization by excluding unnecessary volumes
```

### Scenario 5: High-Frequency Database with Short Retention
```bash
# Database with frequent changes, full backup every 3 days
openstack server set --tag "BACKUP-DAILY-0100-RETAIN90-FULL3" high-frequency-db

# Result: Optimized for frequently changing data
# - Daily backups capture all changes
# - Full backup every 3 days (faster restore)
# - 90-day retention for compliance
```

## Troubleshooting

### Common Issues

#### 1. Authentication Failures

**Problem**: `Authentication failed: Invalid credentials`

**Solutions**:
```bash
# Verify credentials
openstack-backup-automation config-validate

# Test OpenStack CLI directly
openstack --os-cloud default server list

# Check application credential
openstack application credential show <credential-id>

# Verify config.yaml has correct values
cat config.yaml | grep -A 5 "openstack:"
```

#### 2. No Backups Being Created

**Problem**: System runs but no backups are created

**Solutions**:
```bash
# Check if resources are tagged correctly
openstack server list --long | grep -i backup
openstack volume list --long

# Verify resources are discovered
openstack-backup-automation run --status

# Check if backups are due (timing)
openstack-backup-automation run --dry-run

# Force execution ignoring timing
openstack-backup-automation run --test-mode --dry-run
```

#### 3. Volume Metadata Not Working

**Problem**: Volume backups not triggered despite metadata

**Solutions**:
```bash
# Verify metadata is set correctly (use "backup" as key)
openstack volume show <volume-id> -f json | grep -A 5 metadata

# Correct format:
openstack volume set --property backup="BACKUP-DAILY-0300" <volume-id>

# NOT supported (wrong key):
openstack volume set --property schedule="BACKUP-DAILY-0300" <volume-id>
```

#### 4. Backup Verification Timeout

**Problem**: `Backup verification timed out`

**Solutions**:
```bash
# Increase timeout in config.yaml
backup:
  operation_timeout_minutes: 120  # Increase from 60

# Check OpenStack backup status manually
openstack volume backup list --status creating

# Check system load
openstack quota show
```

#### 5. Database Locked Errors

**Problem**: `database is locked`

**Solutions**:
```bash
# Check if another instance is running
ps aux | grep backup-automation

# Stop any running instances
pkill -f backup-automation

# Clean up stale lock files
rm -f backup.db-journal

# Restart the service
systemctl restart backup-automation.timer
```

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