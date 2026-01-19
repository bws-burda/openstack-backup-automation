"""
OpenStack Backup Automation System

A Python-based solution for automated backup and snapshot operations
for OpenStack resources based on tags.
"""

__version__ = "0.1.0"
__author__ = "OpenStack Backup Automation Team"

from .backup import BackupEngine

# Core modules
from .config import ConfigurationManager
from .notification import NotificationService
from .retention import RetentionManager
from .scanner import TagScanner
from .scheduler import ExecutionCoordinator
from .state import StateManager

__all__ = [
    "ConfigurationManager",
    "TagScanner",
    "BackupEngine",
    "RetentionManager",
    "NotificationService",
    "StateManager",
    "ExecutionCoordinator",
]
