#!/bin/bash
# OpenStack Backup Automation Installation Script
# This script installs the backup automation system with proper permissions and configuration

set -e

# Default values
USER="backup"
CONFIG_DIR="/etc/backup-automation"
DATA_DIR="/var/lib/backup-automation"
INSTALL_TYPE=""
PYTHON_CMD="python3"

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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Show usage information
show_usage() {
    cat << EOF
OpenStack Backup Automation Installation Script

Usage: $0 [OPTIONS]

Options:
    --systemd           Install as systemd service (recommended)
    --cron              Install as cron job
    --user USER         System user for the service (default: backup)
    --config-dir DIR    Configuration directory (default: /etc/backup-automation)
    --data-dir DIR      Data directory (default: /var/lib/backup-automation)
    --python PYTHON     Python command (default: python3)
    --help              Show this help message

Examples:
    # Install as systemd service (recommended)
    sudo $0 --systemd

    # Install as cron job with custom user
    sudo $0 --cron --user mybackup

    # Install with custom directories
    sudo $0 --systemd --config-dir /opt/backup/config --data-dir /opt/backup/data

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --systemd)
                INSTALL_TYPE="systemd"
                shift
                ;;
            --cron)
                INSTALL_TYPE="cron"
                shift
                ;;
            --user)
                USER="$2"
                shift 2
                ;;
            --config-dir)
                CONFIG_DIR="$2"
                shift 2
                ;;
            --data-dir)
                DATA_DIR="$2"
                shift 2
                ;;
            --python)
                PYTHON_CMD="$2"
                shift 2
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

    if [[ -z "$INSTALL_TYPE" ]]; then
        print_error "Please specify installation type: --systemd or --cron"
        show_usage
        exit 1
    fi
}

# Check system requirements
check_requirements() {
    print_info "Checking system requirements..."

    # Check Python
    if ! command -v "$PYTHON_CMD" &> /dev/null; then
        print_error "Python 3 is required but not found. Please install Python 3.8 or later."
        exit 1
    fi

    # Check Python version
    PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [[ $(echo "$PYTHON_VERSION < 3.8" | bc -l) -eq 1 ]]; then
        print_error "Python 3.8 or later is required. Found: $PYTHON_VERSION"
        exit 1
    fi

    print_info "Python $PYTHON_VERSION found"

    # Check pip
    if ! $PYTHON_CMD -m pip --version &> /dev/null; then
        print_error "pip is required but not found. Please install pip for Python 3."
        exit 1
    fi

    # Check systemd if installing systemd service
    if [[ "$INSTALL_TYPE" == "systemd" ]] && ! command -v systemctl &> /dev/null; then
        print_error "systemd is required for systemd installation but not found."
        exit 1
    fi

    print_info "System requirements satisfied"
}

# Create system user
create_user() {
    print_info "Creating system user '$USER'..."

    if id "$USER" &>/dev/null; then
        print_info "User '$USER' already exists"
    else
        useradd --system --shell /bin/false --home-dir "$DATA_DIR" --create-home "$USER"
        print_info "Created system user '$USER'"
    fi
}

# Create directories
create_directories() {
    print_info "Creating directories..."

    for dir in "$CONFIG_DIR" "$DATA_DIR"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_info "Created directory: $dir"
        else
            print_info "Directory already exists: $dir"
        fi

        # Set ownership and permissions
        chown "$USER:$USER" "$dir"
        chmod 750 "$dir"
    done
}

# Install Python package
install_package() {
    print_info "Installing OpenStack Backup Automation package..."

    # Check if we're in the source directory
    if [[ -f "setup.py" && -f "requirements.txt" ]]; then
        print_info "Installing from source directory..."
        $PYTHON_CMD -m pip install -e .
    else
        print_error "setup.py not found. Please run this script from the project root directory."
        exit 1
    fi

    print_info "Package installed successfully"
}

# Install systemd service
install_systemd() {
    print_info "Installing systemd service..."

    # Create service file
    cat > /etc/systemd/system/backup-automation.service << EOF
[Unit]
Description=OpenStack Backup Automation
Documentation=https://github.com/example/openstack-backup-automation
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER
Group=$USER
WorkingDirectory=$DATA_DIR
Environment=CONFIG_FILE=$CONFIG_DIR/config.yaml
ExecStart=/usr/local/bin/openstack-backup-automation run
StandardOutput=journal
StandardError=journal
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR
ReadOnlyPaths=$CONFIG_DIR
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

    # Create timer file
    cat > /etc/systemd/system/backup-automation.timer << EOF
[Unit]
Description=Run OpenStack Backup Automation every 15 minutes
Documentation=https://github.com/example/openstack-backup-automation
Requires=backup-automation.service

[Timer]
OnCalendar=*:0/15
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

    # Set permissions
    chmod 644 /etc/systemd/system/backup-automation.service
    chmod 644 /etc/systemd/system/backup-automation.timer

    # Reload systemd
    systemctl daemon-reload

    print_info "Systemd service and timer installed"
    print_info "Service: backup-automation.service"
    print_info "Timer: backup-automation.timer"
}

# Install cron job
install_cron() {
    print_info "Installing cron job..."

    # Create cron file
    cat > /etc/cron.d/backup-automation << EOF
# OpenStack Backup Automation - runs every 15 minutes
*/15 * * * * $USER cd $DATA_DIR && CONFIG_FILE=$CONFIG_DIR/config.yaml /usr/local/bin/openstack-backup-automation run >/dev/null 2>&1
EOF

    chmod 644 /etc/cron.d/backup-automation

    print_info "Cron job installed: /etc/cron.d/backup-automation"
}

# Create example configuration
create_example_config() {
    local config_file="$CONFIG_DIR/config.yaml.example"
    
    print_info "Creating example configuration..."

    cat > "$config_file" << 'EOF'
# OpenStack Backup Automation Configuration
# Copy this file to config.yaml and adjust values for your environment

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
EOF

    chown "$USER:root" "$config_file"
    chmod 640 "$config_file"

    print_info "Example configuration created: $config_file"
}

# Show post-installation instructions
show_post_install() {
    print_info "Installation completed successfully!"
    echo
    print_info "Next steps:"
    echo "1. Copy the example configuration:"
    echo "   cp $CONFIG_DIR/config.yaml.example $CONFIG_DIR/config.yaml"
    echo
    echo "2. Edit the configuration with your OpenStack credentials:"
    echo "   nano $CONFIG_DIR/config.yaml"
    echo
    echo "3. Set proper permissions:"
    echo "   chown $USER:root $CONFIG_DIR/config.yaml"
    echo "   chmod 640 $CONFIG_DIR/config.yaml"
    echo
    echo "4. Test the configuration:"
    echo "   openstack-backup-automation config-validate -c $CONFIG_DIR/config.yaml"
    echo

    if [[ "$INSTALL_TYPE" == "systemd" ]]; then
        echo "5. Enable and start the systemd timer:"
        echo "   systemctl enable backup-automation.timer"
        echo "   systemctl start backup-automation.timer"
        echo
        echo "6. Check service status:"
        echo "   systemctl status backup-automation.timer"
        echo "   systemctl list-timers backup-automation.timer"
    elif [[ "$INSTALL_TYPE" == "cron" ]]; then
        echo "5. The cron job is now active and will run every 15 minutes"
        echo
        echo "6. Check cron logs:"
        echo "   tail -f /var/log/syslog | grep backup-automation"
    fi

    echo
    print_info "For more information, see the documentation at:"
    print_info "https://github.com/example/openstack-backup-automation"
}

# Main installation function
main() {
    print_info "OpenStack Backup Automation Installation"
    print_info "========================================"

    parse_args "$@"
    check_root
    check_requirements
    create_user
    create_directories
    install_package
    
    if [[ "$INSTALL_TYPE" == "systemd" ]]; then
        install_systemd
    elif [[ "$INSTALL_TYPE" == "cron" ]]; then
        install_cron
    fi
    
    create_example_config
    show_post_install
}

# Run main function with all arguments
main "$@"