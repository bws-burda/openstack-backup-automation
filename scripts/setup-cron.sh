#!/bin/bash
# Setup cron job for OpenStack Backup Automation (Repository-based)
# This script creates a cron job that runs from the repository directory

set -e

# Default values
USER="$(whoami)"
REPO_DIR="$(pwd)"
CONFIG_FILE="$REPO_DIR/config.yaml"
INTERVAL=15

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage information
show_usage() {
    cat << EOF
OpenStack Backup Automation Repository Cron Setup Script

Usage: $0 [OPTIONS]

Options:
    --user USER         User for the cron job (default: current user)
    --interval MINUTES  Cron interval in minutes (default: 15)
    --remove            Remove existing cron job
    --help              Show this help message

Examples:
    # Install cron job for current user
    $0

    # Install with custom interval
    $0 --interval 30

    # Remove existing cron job
    $0 --remove

EOF
}

# Parse command line arguments
REMOVE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --user)
            USER="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --remove)
            REMOVE=true
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Remove cron job
if [[ "$REMOVE" == true ]]; then
    print_info "Removing OpenStack Backup Automation cron job..."
    
    # Remove from user's crontab (both comment and command lines)
    (crontab -l 2>/dev/null | grep -v "openstack-backup-automation" | grep -v "# OpenStack Backup Automation" || true) | crontab -
    
    print_info "Cron job removed successfully"
    exit 0
fi

# Validate interval
if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || [[ "$INTERVAL" -lt 1 ]] || [[ "$INTERVAL" -gt 59 ]]; then
    print_error "Invalid interval: $INTERVAL. Must be between 1 and 59 minutes."
    exit 1
fi

# Check if we're in the repository directory
if [[ ! -f "setup.py" ]] || [[ ! -f "config.yaml.example" ]]; then
    print_error "Please run this script from the openstack-backup-automation repository directory."
    exit 1
fi

# Check if configuration file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    print_warn "Configuration file not found: $CONFIG_FILE"
    print_info "Creating configuration from example..."
    
    if [[ -f "config.yaml.example" ]]; then
        cp config.yaml.example config.yaml
        print_info "Configuration template created: $CONFIG_FILE"
        print_warn "Please edit config.yaml with your OpenStack credentials before running backups!"
    else
        print_error "config.yaml.example not found. Cannot create configuration."
        exit 1
    fi
fi

# Detect virtual environment and set command path
VENV_DIR="$REPO_DIR/venv"
if [[ -d "$VENV_DIR" ]] && [[ -f "$VENV_DIR/bin/openstack-backup-automation" ]]; then
    print_info "Detected virtual environment at: $VENV_DIR"
    BACKUP_CMD="$VENV_DIR/bin/openstack-backup-automation"
elif command -v openstack-backup-automation &> /dev/null; then
    print_info "Using system-installed openstack-backup-automation"
    BACKUP_CMD="openstack-backup-automation"
else
    print_info "Installing Python package in development mode..."
    python3 -m pip install -e . --user
    BACKUP_CMD="openstack-backup-automation"
fi

# Calculate cron expression
if [[ "$INTERVAL" == "15" ]]; then
    CRON_TIME="*/15 * * * *"
elif [[ "$INTERVAL" == "30" ]]; then
    CRON_TIME="*/30 * * * *"
elif [[ "$INTERVAL" == "60" ]] || [[ "$INTERVAL" == "1" ]]; then
    CRON_TIME="0 * * * *"
else
    CRON_TIME="*/$INTERVAL * * * *"
fi

print_info "Installing OpenStack Backup Automation cron job..."
print_info "User: $USER"
print_info "Interval: every $INTERVAL minutes"
print_info "Repository: $REPO_DIR"
print_info "Config: $CONFIG_FILE"
print_info "Command: $BACKUP_CMD"

# Create cron entry
CRON_ENTRY="$CRON_TIME $BACKUP_CMD --config $CONFIG_FILE run >/dev/null 2>&1"

# Add to user's crontab (remove any existing entries first, including comments)
(crontab -l 2>/dev/null | grep -v "openstack-backup-automation" | grep -v "# OpenStack Backup Automation" || true; echo "# OpenStack Backup Automation"; echo "$CRON_ENTRY") | crontab -

print_info "Cron job installed successfully!"
print_info "The backup automation will run every $INTERVAL minutes"

# Show next steps
echo
print_info "Next steps:"
echo "1. Edit the configuration file:"
echo "   nano $CONFIG_FILE"
echo
echo "2. Test the backup automation manually:"
echo "   cd $REPO_DIR"
echo "   openstack-backup-automation --config $CONFIG_FILE run --dry-run"
echo
echo "3. Monitor cron execution:"
echo "   tail -f /var/log/syslog | grep CRON"
echo
echo "4. View current crontab:"
echo "   crontab -l"