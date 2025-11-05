"""Notification and error reporting module."""

from .error_handler import (
    BackupErrorHandler,
    ErrorCategory,
    ErrorHandler,
    ErrorSeverity,
    RetryConfig,
)
from .service import NotificationService
from .verification import FailureReporter, OperationVerifier

__all__ = [
    "NotificationService",
    "ErrorHandler",
    "BackupErrorHandler",
    "ErrorCategory",
    "ErrorSeverity",
    "RetryConfig",
    "OperationVerifier",
    "FailureReporter",
]
