# Installation Guide

This guide covers the installation and deployment of OpenStack Backup Automation.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation Methods](#installation-methods)
- [Configuration](#configuration)
- [Deployment Options](#deployment-options)
- [Post-Installation](#post-installation)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 18.04+, CentOS 7+, RHEL 7+, or similar)
- **Python**: 3.8 or later
- **Memory**: Minimum 512MB RAM
- **Disk Space**: 100MB for application, additional space for backup metadata database
- **Network**: Access to OpenStack API endpoints

### OpenStack Requirements

- **OpenStack Version**: Mitaka or later (tested with Queens, Rocky, Stein, Train, Ussuri, Victoria, Wallaby)
- **Required Services**: Nova (Compute), Cinder (Block Storage)
- **Authentication**: Application Credentials (recommended) or Username/Password
- **Permissions**: 
  - Read access to instances and volumes
  - Create/delete snapshots and backups
  - Read project quotas

### Dependencies

The following Python packages are automatically installed:

- `click` - Command-line interface
- `PyYAML` - Configuration file parsing
- `python-openstackclient` - OpenStack API client
- `asyncio` - Asynchronous operations
- `sqlite3` - Database (included in Python standard library)

## Installation Methods

### Method 1: Automated Installation (Recommended)

The automated installation script handles all setup tasks including user creation, directory setup, and service configuration.

```bash
# Clone the repository
git clone https://github.com/example/openstack-backup-automation.git
cd openstack-backup-automation

# Run the installation script
sudo ./scripts/install.sh --systemd

# Or for cron-based installation
sudo ./scripts/install.sh --cron
```

#### Installation Script Options

```bash
sudo ./scripts/install.sh [OPTIONS]

Options:
    --systemd           Install as systemd service (recommended)
    --cron              Install as cron job
    --user USER         System user for the service (default: backup)
    --config-dir DIR    Configuration directory (default: /etc/backup-automation)
    --data-dir DIR      Data directory (default: /var/lib/backup-automation)
    --python PYTHON     Python command (default: python3)
    --help              Show help message
```

### Method 2: Manual Installation

#### Step 1: Install Python Package

```bash
# From source
git clone https://github.com/example/openstack-backup-automation.git
cd openstack-backup-automation
pip3 install -e .

# Or from PyPI (when available)
pip3 install openstack-backup-automation
```

#### Step 2: Create System User

```bash
sudo useradd --system --shell /bin/false --home-dir /var/lib/backup-automation --create-home backup
```

#### Step 3: Create Directories

```bash
sudo mkdir -p /etc/backup-automation /var/lib/backup-automation
sudo chown backup:backup /etc/backup-automation /var/lib/backup-automation
sudo chmod 750 /etc/backup-automation /var/lib/backup-automation
```

#### Step 4: Install Service Files

Choose either systemd or cron installation:

**Systemd Installation:**

```bash
# Copy service files
sudo cp config/systemd/backup-automation.service /etc/systemd/system/
sudo cp config/systemd/backup-automation.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload
```

**Cron Installation:**

```bash
# Create cron job
echo "*/15 * * * * backup cd /var/lib/backup-automation && CONFIG_FILE=/etc/backup-automation/config.yaml /usr/local/bin/openstack-backup-automation run >/dev/null 2>&1" | sudo tee /etc/cron.d/backup-automation
```

### Method 3: Container Installation

```bash
# Build container image
docker build -t openstack-backup-automation .

# Run container
docker run -d \
  --name backup-automation \
  -v /path/to/config.yaml:/etc/backup-automation/config.yaml:ro \
  -v /path/to/data:/var/lib/backup-automation \
  openstack-backup-automation
```

## Configuration

### Step 1: Create Configuration File

```bash
# Copy example configuration
sudo cp /etc/backup-automation/config.yaml.example /etc/backup-automation/config.yaml

# Or create using CLI
openstack-backup-automation config-validate --create-example -o /etc/backup-automation/config.yaml
```

### Step 2: Edit Configuration

Edit `/etc/backup-automation/config.yaml` with your OpenStack credentials and settings:

```yaml
openstack:
  # Use Application Credentials (recommended)
  auth_method: "application_credential"
  application_credential_id: "your-app-credential-id"
  application_credential_secret: "your-app-credential-secret"
  
  # OpenStack endpoints
  auth_url: "https://your-openstack.example.com:5000/v3"
  project_name: "your-project-name"
  project_domain_name: "Default"
  region_name: "RegionOne"

backup:
  full_backup_interval_days: 7
  retention_days: 30
  max_concurrent_operations: 5
  operation_timeout_minutes: 60

notifications:
  email_recipient: "admin@example.com"
  email_sender: "backup-system@example.com"

scheduling:
  mode: "cron"
  check_interval_minutes: 15
```

### Step 3: Set Permissions

```bash
sudo chown backup:root /etc/backup-automation/config.yaml
sudo chmod 640 /etc/backup-automation/config.yaml
```

### Step 4: Validate Configuration

```bash
# Validate configuration and test OpenStack connectivity
openstack-backup-automation config-validate -c /etc/backup-automation/config.yaml

# Or use the validation script
./scripts/validate-config.sh --config /etc/backup-automation/config.yaml
```

## Deployment Options

### Option 1: Systemd Service (Recommended)

Systemd provides reliable service management with automatic restarts and logging.

```bash
# Enable and start the timer
sudo systemctl enable backup-automation.timer
sudo systemctl start backup-automation.timer

# Check status
sudo systemctl status backup-automation.timer
sudo systemctl list-timers backup-automation.timer

# View logs
sudo journalctl -u backup-automation.service -f
```

#### Daemon Mode (Continuous Operation)

For environments requiring continuous monitoring:

```bash
# Install daemon service
sudo cp config/systemd/backup-automation-daemon.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start daemon
sudo systemctl enable backup-automation-daemon.service
sudo systemctl start backup-automation-daemon.service
```

### Option 2: Cron Job

Cron provides simple, reliable scheduling for most environments.

```bash
# Install cron job (if not done during installation)
sudo ./scripts/setup-cron.sh

# Custom interval (every 30 minutes)
sudo ./scripts/setup-cron.sh --interval 30

# Check cron logs
sudo tail -f /var/log/syslog | grep backup-automation
```

### Option 3: Manual Execution

For testing or custom scheduling:

```bash
# Single backup cycle
openstack-backup-automation run -c /etc/backup-automation/config.yaml

# Dry run (show what would be done)
openstack-backup-automation run --dry-run -c /etc/backup-automation/config.yaml

# Check system status
openstack-backup-automation run --status -c /etc/backup-automation/config.yaml
```

## Post-Installation

### 1. Tag Your Resources

Add schedule tags to your OpenStack instances and volumes:

```bash
# Daily snapshots at 3 AM
openstack server set --tag "SNAPSHOT-DAILY-0300" my-server

# Weekly backups on Sunday at midnight
openstack volume set --tag "BACKUP-WEEKLY-0000" my-volume

# Daily backups at 2 AM
openstack volume set --tag "BACKUP-DAILY-0200" my-important-volume
```

### 2. Test the System

```bash
# Run a dry-run to see what would be backed up
sudo -u backup openstack-backup-automation run --dry-run

# Run actual backup cycle
sudo -u backup openstack-backup-automation run

# Check system status
sudo -u backup openstack-backup-automation run --status
```

### 3. Monitor Operations

```bash
# View service logs (systemd)
sudo journalctl -u backup-automation.service -f

# View cron logs
sudo tail -f /var/log/syslog | grep backup-automation

# Check database for backup history
sudo -u backup sqlite3 /var/lib/backup-automation/backups.db "SELECT * FROM backups ORDER BY created_at DESC LIMIT 10;"
```

### 4. Set Up Monitoring

Configure your monitoring system to check:

- Service status: `systemctl is-active backup-automation.timer`
- Last successful backup time
- Error notifications via email
- Disk space in data directory

## Troubleshooting

### Common Issues

#### 1. Authentication Failures

```bash
# Test OpenStack connectivity
openstack-backup-automation config-validate

# Check credentials
openstack --os-cloud default server list

# Verify application credential permissions
openstack application credential show <credential-id>
```

#### 2. Permission Errors

```bash
# Check file permissions
ls -la /etc/backup-automation/
ls -la /var/lib/backup-automation/

# Fix permissions
sudo chown -R backup:backup /var/lib/backup-automation/
sudo chown backup:root /etc/backup-automation/config.yaml
sudo chmod 640 /etc/backup-automation/config.yaml
```

#### 3. Service Not Running

```bash
# Check systemd service status
sudo systemctl status backup-automation.timer
sudo systemctl status backup-automation.service

# Check cron job
sudo crontab -l -u backup
cat /etc/cron.d/backup-automation

# View detailed logs
sudo journalctl -u backup-automation.service --no-pager
```

#### 4. Database Issues

```bash
# Check database file
sudo -u backup ls -la /var/lib/backup-automation/

# Recreate database (will lose history)
sudo -u backup rm /var/lib/backup-automation/backups.db
sudo -u backup openstack-backup-automation run --dry-run
```

### Log Locations

- **Systemd logs**: `journalctl -u backup-automation.service`
- **Cron logs**: `/var/log/syslog` or `/var/log/cron`
- **Application logs**: Configured via systemd or cron output
- **Database**: `/var/lib/backup-automation/backups.db`

### Getting Help

1. **Check logs** for error messages
2. **Validate configuration** with `config-validate` command
3. **Test connectivity** to OpenStack APIs
4. **Review permissions** for files and directories
5. **Check resource tags** are properly formatted

For additional support, please refer to the project documentation or open an issue on GitHub.

## Security Considerations

### File Permissions

- Configuration files: `640` (readable by backup user and root)
- Data directory: `750` (writable by backup user only)
- Service files: `644` (standard system file permissions)

### Network Security

- Use HTTPS for all OpenStack API communication
- Consider firewall rules for OpenStack API access
- Use Application Credentials instead of user passwords
- Regularly rotate credentials

### Monitoring

- Monitor for authentication failures
- Set up alerts for backup failures
- Review backup success rates regularly
- Monitor disk space usage