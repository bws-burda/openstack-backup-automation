#!/bin/bash
# Cleanup script for Python cache files

echo "🧹 Cleaning up Python cache files..."

# Remove all __pycache__ directories
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Remove .pyc files
find . -name "*.pyc" -delete 2>/dev/null || true

# Remove .pyo files
find . -name "*.pyo" -delete 2>/dev/null || true

# Remove .pytest_cache
rm -rf .pytest_cache 2>/dev/null || true

# Remove any temporary files (but not swap files or backup.db)
find . -name "*~" -delete 2>/dev/null || true

echo "✅ Cleanup completed!"
echo ""
echo "Removed:"
echo "  - All __pycache__ directories"
echo "  - All .pyc/.pyo files"
echo "  - .pytest_cache directory"
echo "  - Temporary files (*~)"
echo ""
echo "Preserved:"
echo "  - TODO.md (kept as requested)"
echo "  - backup.db (kept as requested)"
echo "  - Vim swap files (kept as requested)"