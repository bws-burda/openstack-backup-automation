# OpenStack Backup Automation

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Built with vibe coding.

Automated backup and snapshot system for OpenStack resources based on tags.

## 📋 Quick Navigation

- [Quick Start](#quick-start-repository-based) - Get up and running in 5 minutes
- [Requirements](#requirements) - System and dependency requirements
- [Tag Your Resources](#tag-your-resources) - How to tag instances and volumes
- [Tag Format](#tag-format) - Complete tag syntax reference
- [Real-World Examples](#real-world-examples) - Practical tagging scenarios
- [Manual Execution](#manual-execution) - Run backups manually
- [Setup Automatic Execution](#setup-automatic-execution) - Configure cron jobs
- [Backup Strategy](#backup-strategy) - How backups work
- [Skip Logic](#skip-logic---concurrent-operation-protection) - Concurrent operation handling
- [Monitoring](#monitoring) - Monitor your backups
- [Retention Management](#retention-management) - Automatic cleanup
- [Features](#features) - What's included
- [Troubleshooting](#troubleshooting) - Common issues and solutions
- [Development](#development) - Contributing to the project
- [Roadmap](#-planned-features) - Planned features

## Quick Start (Repository-based)

### Requirements
- Linux OS
- Python 3.8+
- Valid OpenStack credentials
- SMTP access for notifications (optional)

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

### Real-World Examples

**Production Database Server**
```bash
# Daily backups at 2 AM, keep 1 year, full backup every 7 days
openstack server set --tag "BACKUP-DAILY-0200-RETAIN365-FULL7" prod-database
```

**Web Server Farm**
```bash
# Daily snapshots at 3 AM, keep 30 days
openstack server set --tag "SNAPSHOT-DAILY-0300-RETAIN30" web-server-01
openstack server set --tag "SNAPSHOT-DAILY-0300-RETAIN30" web-server-02
```

**Development Environment**
```bash
# Weekly snapshots on Sunday at 1 AM, keep 2 weeks
openstack server set --tag "SNAPSHOT-SUNDAY-0100-RETAIN14" dev-environment
```

**File Server**
```bash
# Weekly backups on Saturday at midnight, keep 6 months, full backup every time
openstack server set --tag "BACKUP-SATURDAY-0000-RETAIN180-FULL1" file-server
```

**Test/Staging Environment**
```bash
# Daily snapshots at 4 AM, keep 1 week
openstack server set --tag "SNAPSHOT-DAILY-0400-RETAIN7" staging-server
```

**Archive Storage**
```bash
# Monthly backups on 1st at midnight, keep 7 years, full backup every time
openstack volume set --property backup="BACKUP-MONTHLY-0000-RETAIN2555-FULL1" archive-volume
```

**High-Frequency Database**
```bash
# Daily backups at 1 AM, keep 3 months, full backup every 3 days
openstack server set --tag "BACKUP-DAILY-0100-RETAIN90-FULL3" high-freq-db
```

## Manual Execution

```bash
# Dry run (shows what would be done)
openstack-backup-automation run --dry-run

# Run backup cycle
openstack-backup-automation run

# Check system health
openstack-backup-automation health
```

## Setup Automatic Execution
```bash
# Setup cron job (runs every 15 minutes by default unless otherwise configured)
./scripts/setup-cron.sh

# Or with custom interval
./scripts/setup-cron.sh --interval 30
```

### Manual Testing

#### Test Mode to trigger backups immediately
```bash
# Test mode with dry run - safe testing without creating actual backups
openstack-backup-automation run --test-mode --dry-run

# Test mode - ignore timing, execute all policies
openstack-backup-automation run --test-mode
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

## Skip Logic - Concurrent Operation Protection

When multiple backup cycles run in parallel (e.g., cron every 15 minutes), the system automatically skips operations if a volume is already being backed up. This prevents "volume already backing up" errors and allows safe, frequent scheduling.

### How It Works

- **Status Check**: Before creating a backup/snapshot, the system checks if the volume status is "backing-up"
- **Automatic Skip**: If a backup is already in progress, the operation is skipped
- **Retry Next Cycle**: The operation will be automatically retried in the next backup cycle
- **No Error**: Skipped operations are NOT counted as failures and do NOT trigger monitoring alerts

### Example Scenario

```bash
# Cron: Every 15 minutes

10:00 AM - Cycle 1 starts
  - Volume A: Backup starts (status: backing-up)
  - Backup takes 20 minutes

10:15 AM - Cycle 2 starts (while Cycle 1 still running)
  - Volume A: SKIPPED (already backing-up)
  - Will retry at 10:30 AM

10:30 AM - Cycle 3 starts
  - Volume A: Backup completes from Cycle 1
  - Volume A: New backup starts (status: backing-up)
```

### Output Example

```
Backup cycle completed:
  Operations executed: 10
  Successful: 8
  Skipped: 2
  Failed: 0
```

### Benefits

- **Frequent Cron Schedules**: Safe to use frequent schedules (e.g., every 15 minutes)
- **No Conflicts**: Prevents concurrent operation errors automatically
- **Transparent Retry**: Skipped operations are automatically retried without manual intervention
- **Monitoring-Friendly**: Skipped operations do NOT trigger error alerts

## Features

- ✅ Tag-based resource discovery
- ✅ **Defensive backup strategy** (immediate protection)
- ✅ **Concurrent operation protection** (skip if already backing up)
- ✅ Automated snapshots and backups
- ✅ Configurable retention policies
- ✅ Parallel operation execution
- ✅ Email notifications on errors (full reports optional)
- ✅ Cron integration
- ✅ Comprehensive logging
- ✅ Health monitoring

## Retention Management

The system automatically manages backup retention with intelligent policies and automatic cleanup.

### Tag-Based Retention (Recommended)

Specify retention directly in tags:

```bash
# Keep backups for 90 days
openstack server set --tag "BACKUP-DAILY-0300-RETAIN90" my-server

# Keep backups for 14 days
openstack volume set --property backup="BACKUP-DAILY-0400-RETAIN14" my-volume
```

### Policy Priority

Retention policies are applied in this order (highest to lowest priority):

1. **Tag-Embedded Retention**: `RETAIN{n}` in tag (e.g., `RETAIN90`)
2. **Global Policies**: Configured in `config.yaml` by type/frequency
3. **Default Policy**: Fallback retention (default: 30 days)

### Configuration

```yaml
# config.yaml
retention_policies:
  default:
    retention_days: 30
    min_backups_to_keep: 1
  
  snapshots:
    retention_days: 7
  
  daily:
    retention_days: 30
    min_backups_to_keep: 3
  
  weekly:
    retention_days: 60
    min_backups_to_keep: 2
```

### Automatic Chain Integrity

The system protects backup chains automatically:

- ✅ **Full Backup Protection**: Full backups are only deleted when no incremental backups depend on them
- ✅ **Complete Chains**: Incremental chains remain complete and functional
- ✅ **Orphan Detection**: Orphaned incrementals are automatically identified and cleaned up
- ✅ **Minimum Retention**: At least 1 backup is always kept per resource

### Performance: Batch Deletion

Backups are deleted in parallel batches for improved performance:

| Backup Count | Sequential | Batch (5) | Improvement |
|--------------|------------|-----------|-------------|
| 50           | 1:40 min   | 1:20 min  | 20% faster  |
| 200          | 6:40 min   | 5:20 min  | 25% faster  |
| 1000         | 33 min     | 27 min    | 30% faster  |

### Best Practices

1. **Use Tag Retention**: Always specify `RETAIN{n}` for important resources
2. **Conservative Defaults**: Set default policy to longer retention (e.g., 30 days)
3. **Monitor Cleanup**: Check logs for deletion operations
4. **Test Policies**: Use `--dry-run` to preview what would be deleted

# Roadmap

## 🚀 Planned Features

### Full Incremental Backup Chain Management

**Status:** Pending

**Goal:** Implement intelligent full/incremental backup chains to optimize storage usage.

**Current State:**
- Tag format already supports `FULL{DAYS}` parameter (e.g., `BACKUP-DAILY-0300-FULL7`)
- Config has `full_backup_interval_days` setting
- Database tracks backup types (full/incremental)
- Naming is already prepared

**What's Missing:**
- Scheduling of incremental backups
- Chain integrity checks (detect broken chains)
- Smart cleanup that preserves chain integrity

**Example Target Behavior:**
```bash
# Tag: BACKUP-DAILY-0300-FULL7
Day 1: Full backup
Day 2-7: Incremental backups (based on Day 1)
Day 8: Full backup (new chain starts)
Day 9-14: Incremental backups (based on Day 8)
```

**Benefits:**
- Significant storage savings (incrementals are much smaller)
- Faster backup operations (incrementals are quicker)
- Configurable balance between storage and restore speed

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
