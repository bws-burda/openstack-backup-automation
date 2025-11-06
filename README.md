# OpenStack Backup Automation

![Tests](https://github.com/your-username/openstack-backup-automation/workflows/Tests/badge.svg)
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
python3 -m src.cli.main config-validate

# Test run (dry-run)
python3 -m src.cli.main run --dry-run
```

### 5. Setup Automatic Execution
```bash
# Setup cron job (runs every 15 minutes)
./scripts/setup-repo-cron.sh

# Or with custom interval
./scripts/setup-repo-cron.sh --interval 30
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

### Volume Tags
```bash
# Daily volume backups at 04:00, keep 60 days (single volume)
openstack volume set --tag "BACKUP-DAILY-0400-RETAIN60" my-important-volume

# Note: If you tag an instance with BACKUP-*, all attached volumes 
# are automatically included. Individual volume tags are only needed
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
python3 -m src.cli.main config-validate

# Dry run (test mode - shows what would be done)
python3 -m src.cli.main run --dry-run

# Run backup cycle
python3 -m src.cli.main run

# Check system health
python3 -m src.cli.main health
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
```bash
# Check database contents
sqlite3 backup.db "SELECT backup_id, resource_id, backup_type, created_at FROM backups ORDER BY created_at;"

# Clean up cache files
./cleanup_cache.sh
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
./scripts/setup-repo-cron.sh --remove
```

## System Installation (Alternative)

For system-wide installation with systemd:

```bash
sudo ./scripts/install.sh --systemd
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
- ✅ Cron and systemd integration
- ✅ Comprehensive logging
- ✅ Health monitoring

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

## Requirements

- Python 3.8+
- Valid OpenStack credentials
- SMTP access for notifications (optional)

## License

MIT License