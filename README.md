# OpenStack Backup Automation

Automated backup and snapshot system for OpenStack resources based on tags.

## Quick Start (Repository-based)

### 1. Clone and Setup
```bash
git clone <repository-url> openstack-backup-automation
cd openstack-backup-automation
```

### 2. Install Dependencies
```bash
# Install Python dependencies
pip3 install -e . --user

# Or create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 3. Configure
```bash
# Copy example configuration
cp config.yaml.example config.yaml

# Edit with your OpenStack credentials
nano config.yaml
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
# Daily snapshots at 03:00
openstack server set --tag "SNAPSHOT-DAILY-0300" my-web-server

# Weekly backups on Monday at 02:00
openstack server set --tag "BACKUP-WEEKLY-0200" my-database-server

# Monthly backups on 1st at 01:00
openstack server set --tag "BACKUP-MONTHLY-0100" my-storage-server
```

### Volume Tags
```bash
# Daily volume backups at 04:00, keep 60 days
openstack volume set --tag "BACKUP-DAILY-0400-RETAIN60" my-important-volume
```

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

notifications:
  email_recipient: "admin@example.com"
  email_sender: "backup-system@example.com"

backup:
  retention_days: 30
  max_concurrent_operations: 5
```

## Manual Execution

```bash
# Run backup cycle
python3 -m src.cli.main run

# Dry run (test mode)
python3 -m src.cli.main run --dry-run

# Check system health
python3 -m src.cli.main health

# Validate configuration
python3 -m src.cli.main config-validate
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

## Features

- ✅ Tag-based resource discovery
- ✅ Automated snapshots and backups
- ✅ Full/Incremental backup strategies
- ✅ Configurable retention policies
- ✅ Parallel operation execution
- ✅ Email notifications on errors
- ✅ Cron and systemd integration
- ✅ Comprehensive logging
- ✅ Health monitoring

## Requirements

- Python 3.8+
- OpenStack SDK
- Valid OpenStack credentials
- SMTP access for notifications (optional)

## License

MIT License