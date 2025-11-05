#!/bin/bash
# Pre-push checks - Run the same checks as GitHub Actions locally

set -e  # Exit on any error

echo "🔍 Running pre-push checks..."
echo "================================"

# Check if we're in the right directory
if [ ! -f "config.yaml.example" ]; then
    echo "❌ Error: Run this script from the project root directory"
    exit 1
fi

# Check if development dependencies are installed
echo "📦 Checking development dependencies..."
if ! command -v pytest &> /dev/null || ! command -v flake8 &> /dev/null || ! command -v black &> /dev/null; then
    echo "❌ Development dependencies not found. Please install them first:"
    echo "   pip install -r requirements-dev.txt"
    exit 1
fi

echo ""
echo "1️⃣  Running unit tests..."
python -m pytest tests/ -v --tb=short

echo ""
echo "2️⃣  Checking for critical syntax errors..."
flake8 src --count --select=E9,F63,F7,F82 --show-source --statistics

echo ""
echo "3️⃣  Running code style checks..."
flake8 src --count --exit-zero --statistics

echo ""
echo "4️⃣  Checking code formatting..."
if black --check --diff src/; then
    echo "✅ Code formatting is correct"
else
    echo "❌ Code formatting issues found. Run 'black src/' to fix."
    exit 1
fi

echo ""
echo "5️⃣  Checking import sorting..."
if isort --check-only --diff src/; then
    echo "✅ Import sorting is correct"
else
    echo "❌ Import sorting issues found. Run 'isort src/' to fix."
    exit 1
fi

echo ""
echo "6️⃣  Validating configuration..."
python -c "
from src.config.manager import ConfigurationManager
import tempfile, shutil, os

# Copy example config to temporary file
shutil.copy('config.yaml.example', 'test-config.yaml')

try:
    manager = ConfigurationManager()
    config = manager.load_config('test-config.yaml')
    print('✅ Configuration file syntax is valid')
except Exception as e:
    if 'OpenStack' in str(e) or 'connection' in str(e).lower():
        print('✅ Configuration syntax valid (OpenStack connection expected to fail)')
    else:
        print(f'❌ Configuration validation failed: {e}')
        raise e
finally:
    if os.path.exists('test-config.yaml'):
        os.remove('test-config.yaml')
"

echo ""
echo "🎉 All pre-push checks passed!"
echo "✅ Ready to push to GitHub"