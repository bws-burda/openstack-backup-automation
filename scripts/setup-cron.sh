#!/bin/bash
# Setup cron job for OpenStack Backup Automation
# This script creates a cron job that runs the backup automation every 15 minutes

set -e

# Default values
USER="backup"
CONFIG_FILE="/etc/backup-automation/config.yaml"
DATA_DIR="/var/lib/backup-automation"

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
OpenStack Backup Automation Cron Setup Script

Usage: $0 [OPTIONS]

Options:
    --user USER         System user for the cron job (default: backup)
    --config FILE       Configuration file path (default: /etc/backup-automation/config.yaml)
    --data-dir DIR      Data directory (default: /var/lib/backup-automation)
    --interval MINUTES  Cron interval in minutes (default: 15)
    --remove            Remove existing cron job
    --help              Show this help message

Examples:
    # Install cron job with defaults
    sudo $0

    # Install with custom user and interval
    sudo $0 --user mybackup --interval 30

    # Remove existing cron job
    sudo $0 --remove

EOF
}

# Parse command line arguments
INTERVAL=15
REMOVE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --user)
            USER="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --data-dir)
            DATA_DIR="$2"
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

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Remove cron job
if [[ "$REMOVE" == true ]]; then
    print_info "Removing OpenStack Backup Automation cron job..."
    
    if [[ -f /etc/cron.d/backup-automation ]]; then
        rm /etc/cron.d/backup-automation
        print_info "Cron job removed successfully"
    else
        print_warn "Cron job not found"
    fi
    
    exit 0
fi

# Validate interval
if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || [[ "$INTERVAL" -lt 1 ]] || [[ "$INTERVAL" -gt 59 ]]; then
    print_error "Invalid interval: $INTERVAL. Must be between 1 and 59 minutes."
    exit 1
fi

# Check if user exists
if ! id "$USER" &>/dev/null; then
    print_error "User '$USER' does not exist. Please create the user first or specify an existing user."
    exit 1
fi

# Check if configuration file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    print_warn "Configuration file not found: $CONFIG_FILE"
    print_warn "Make sure to create the configuration file before the cron job runs."
fi

# Check if data directory exists
if [[ ! -d "$DATA_DIR" ]]; then
    print_warn "Data directory not found: $DATA_DIR"
    print_warn "Make sure the data directory exists and is writable by user '$USER'."
fi

# Create cron job
print_info "Installing OpenStack Backup Automation cron job..."
print_info "User: $USER"
print_info "Interval: every $INTERVAL minutes"
print_info "Config: $CONFIG_FILE"
print_info "Data directory: $DATA_DIR"

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

# Create cron file
cat > /etc/cron.d/backup-automation << EOF
# OpenStack Backup Automation
# Runs every $INTERVAL minutes
# Generated on $(date)

SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

$CRON_TIME $USER cd $DATA_DIR && CONFIG_FILE=$CONFIG_FILE /usr/local/bin/openstack-backup-automation run >/dev/null 2>&1
EOF

# Set proper permissions
chmod 644 /etc/cron.d/backup-automation

print_info "Cron job installed successfully: /etc/cron.d/backup-automation"
print_info "The backup automation will run every $INTERVAL minutes as user '$USER'"

# Show next steps
echo
print_info "Next steps:"
echo "1. Ensure the configuration file exists and is properly configured:"
echo "   $CONFIG_FILE"
echo
echo "2. Test the backup automation manually:"
echo "   sudo -u $USER CONFIG_FILE=$CONFIG_FILE openstack-backup-automation run --dry-run"
echo
echo "3. Monitor cron execution:"
echo "   tail -f /var/log/syslog | grep CRON"
echo
echo "4. Check backup automation logs:"
echo "   journalctl -f -t openstack-backup-automation"