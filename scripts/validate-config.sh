#!/bin/bash
# Configuration validation script for OpenStack Backup Automation
# This script validates the configuration file and tests OpenStack connectivity

set -e

# Default values
CONFIG_FILE="./config.yaml"
VERBOSE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_debug() {
    if [[ "$VERBOSE" == true ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

# Show usage information
show_usage() {
    cat << EOF
OpenStack Backup Automation Configuration Validator

Usage: $0 [OPTIONS]

Options:
    --config FILE       Configuration file to validate (default: ./config.yaml)
    --verbose           Enable verbose output
    --help              Show this help message

Examples:
    # Validate default configuration
    $0

    # Validate specific configuration file
    $0 --config /etc/backup-automation/config.yaml

    # Validate with verbose output
    $0 --config config.yaml --verbose

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
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

# Check if configuration file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    print_error "Configuration file not found: $CONFIG_FILE"
    exit 1
fi

print_info "Validating configuration file: $CONFIG_FILE"

# Check if Python and required modules are available
print_debug "Checking Python environment..."

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not found"
    exit 1
fi

# Try to validate using the CLI tool
print_info "Running configuration validation..."

if command -v openstack-backup-automation &> /dev/null; then
    # Use the installed CLI tool
    print_debug "Using installed openstack-backup-automation CLI"
    if openstack-backup-automation config-validate --config "$CONFIG_FILE"; then
        print_info "✓ Configuration validation passed"
    else
        print_error "Configuration validation failed"
        exit 1
    fi
else
    # Try to run from source directory
    print_debug "CLI not installed, trying to run from source"
    
    if [[ -f "src/cli/main.py" ]]; then
        if python3 -m src.cli.main config-validate --config "$CONFIG_FILE"; then
            print_info "✓ Configuration validation passed"
        else
            print_error "Configuration validation failed"
            exit 1
        fi
    else
        print_error "Cannot find openstack-backup-automation CLI tool"
        print_error "Please install the package or run from the source directory"
        exit 1
    fi
fi

print_info "Configuration validation completed successfully"