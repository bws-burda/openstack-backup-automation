"""Comprehensive error handling with retry logic and exponential backoff."""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

from ..backup.models import OperationResult, OperationStatus
from ..interfaces import NotificationServiceInterface


class ErrorSeverity(Enum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for handling strategies."""

    AUTHENTICATION = "authentication"
    NETWORK = "network"
    QUOTA = "quota"
    RESOURCE_NOT_FOUND = "resource_not_found"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for error handling."""

    operation: str
    resource_id: str
    resource_type: str
    resource_name: str
    attempt_number: int = 1
    max_attempts: int = 5
    additional_info: Optional[Dict[str, Any]] = None


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 5
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 300.0  # Maximum delay in seconds (5 minutes)
    exponential_base: float = 2.0
    jitter: bool = True  # Add random jitter to prevent thundering herd


class ErrorHandler:
    """Comprehensive error handler with categorization and retry logic."""

    def __init__(
        self, notification_service: Optional[NotificationServiceInterface] = None
    ):
        self.notification_service = notification_service
        self.logger = logging.getLogger(__name__)

        # Define which error types are retryable
        self.retryable_categories = {
            ErrorCategory.NETWORK,
            ErrorCategory.TIMEOUT,
            ErrorCategory.SYSTEM,
        }

        # Define error severity mapping
        self.severity_mapping = {
            ErrorCategory.AUTHENTICATION: ErrorSeverity.CRITICAL,
            ErrorCategory.PERMISSION: ErrorSeverity.HIGH,
            ErrorCategory.QUOTA: ErrorSeverity.HIGH,
            ErrorCategory.RESOURCE_NOT_FOUND: ErrorSeverity.MEDIUM,
            ErrorCategory.NETWORK: ErrorSeverity.MEDIUM,
            ErrorCategory.TIMEOUT: ErrorSeverity.MEDIUM,
            ErrorCategory.SYSTEM: ErrorSeverity.HIGH,
            ErrorCategory.UNKNOWN: ErrorSeverity.MEDIUM,
        }

    def categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize an error based on its type and message."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        # Authentication errors
        if any(
            keyword in error_str
            for keyword in ["auth", "credential", "unauthorized", "401"]
        ):
            return ErrorCategory.AUTHENTICATION

        # Network errors
        if any(
            keyword in error_str
            for keyword in ["network", "connection", "dns", "resolve"]
        ) or any(
            keyword in error_type for keyword in ["connection", "socket", "timeout"]
        ):
            return ErrorCategory.NETWORK

        # Quota/limit errors
        if any(
            keyword in error_str for keyword in ["quota", "limit", "exceeded", "413"]
        ):
            return ErrorCategory.QUOTA

        # Resource not found
        if any(
            keyword in error_str for keyword in ["not found", "404", "does not exist"]
        ):
            return ErrorCategory.RESOURCE_NOT_FOUND

        # Permission errors
        if any(keyword in error_str for keyword in ["permission", "forbidden", "403"]):
            return ErrorCategory.PERMISSION

        # Timeout errors
        if any(keyword in error_str for keyword in ["timeout", "timed out"]):
            return ErrorCategory.TIMEOUT

        # System errors (database, file system, etc.)
        if any(
            keyword in error_type
            for keyword in ["os", "io", "file", "database", "sqlite"]
        ):
            return ErrorCategory.SYSTEM

        return ErrorCategory.UNKNOWN

    def get_error_severity(self, category: ErrorCategory) -> ErrorSeverity:
        """Get the severity level for an error category."""
        return self.severity_mapping.get(category, ErrorSeverity.MEDIUM)

    def is_retryable(self, error: Exception, context: ErrorContext) -> bool:
        """Determine if an error should be retried."""
        if context.attempt_number >= context.max_attempts:
            return False

        category = self.categorize_error(error)
        return category in self.retryable_categories

    def calculate_delay(self, attempt: int, config: RetryConfig) -> float:
        """Calculate delay for exponential backoff with jitter."""
        delay = min(
            config.base_delay * (config.exponential_base ** (attempt - 1)),
            config.max_delay,
        )

        if config.jitter:
            # Add ±25% jitter
            import random

            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(delay, 0.1)  # Minimum 0.1 second delay

    async def handle_error(
        self,
        error: Exception,
        context: ErrorContext,
        operation_result: Optional[OperationResult] = None,
    ) -> bool:
        """
        Handle an error with appropriate logging, notification, and retry logic.

        Returns:
            bool: True if the error was handled and operation should be retried, False otherwise
        """
        category = self.categorize_error(error)
        severity = self.get_error_severity(category)

        # Log the error with appropriate level
        log_message = (
            f"Error in {context.operation} for {context.resource_type} "
            f"{context.resource_id} (attempt {context.attempt_number}/{context.max_attempts}): "
            f"{error} [Category: {category.value}, Severity: {severity.value}]"
        )

        if severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
            self.logger.error(log_message)
        elif severity == ErrorSeverity.MEDIUM:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

        # Update operation result if provided
        if operation_result:
            operation_result.status = OperationStatus.FAILED
            operation_result.error_message = str(error)

        # Send notification for critical and high severity errors
        if (
            severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]
            and self.notification_service
        ):
            notification_context = {
                "operation": context.operation,
                "resource_id": context.resource_id,
                "resource_type": context.resource_type,
                "resource_name": context.resource_name,
                "attempt_number": context.attempt_number,
                "max_attempts": context.max_attempts,
                "error_category": category.value,
                "error_severity": severity.value,
            }

            if context.additional_info:
                notification_context.update(context.additional_info)

            try:
                self.notification_service.send_error_notification(
                    error, notification_context
                )
            except Exception as notification_error:
                self.logger.error(
                    f"Failed to send error notification: {notification_error}"
                )

        # Determine if retry should be attempted
        return self.is_retryable(error, context)

    async def execute_with_retry(
        self,
        operation: Callable,
        context: ErrorContext,
        retry_config: Optional[RetryConfig] = None,
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute an operation with retry logic and error handling.

        Args:
            operation: The async function to execute
            context: Error context information
            retry_config: Retry configuration (uses defaults if None)
            *args, **kwargs: Arguments to pass to the operation

        Returns:
            The result of the operation if successful

        Raises:
            The last exception if all retries are exhausted
        """
        if retry_config is None:
            retry_config = RetryConfig()

        context.max_attempts = retry_config.max_attempts
        last_exception = None

        for attempt in range(1, retry_config.max_attempts + 1):
            context.attempt_number = attempt

            try:
                self.logger.debug(
                    f"Executing {context.operation} for {context.resource_type} "
                    f"{context.resource_id} (attempt {attempt}/{retry_config.max_attempts})"
                )

                result = await operation(*args, **kwargs)

                if attempt > 1:
                    self.logger.info(
                        f"Operation {context.operation} succeeded on attempt {attempt} "
                        f"for {context.resource_type} {context.resource_id}"
                    )

                return result

            except Exception as e:
                last_exception = e

                should_retry = await self.handle_error(e, context)

                if not should_retry or attempt == retry_config.max_attempts:
                    break

                # Calculate and apply delay before retry
                delay = self.calculate_delay(attempt, retry_config)
                self.logger.info(
                    f"Retrying {context.operation} for {context.resource_type} "
                    f"{context.resource_id} in {delay:.1f} seconds"
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        self.logger.error(
            f"All retry attempts exhausted for {context.operation} "
            f"on {context.resource_type} {context.resource_id}"
        )

        raise last_exception


class BackupErrorHandler(ErrorHandler):
    """Specialized error handler for backup operations."""

    def __init__(
        self, notification_service: Optional[NotificationServiceInterface] = None
    ):
        super().__init__(notification_service)

        # Backup-specific retry configuration
        self.backup_retry_config = RetryConfig(
            max_attempts=3,  # Fewer attempts for backup operations
            base_delay=2.0,  # Longer base delay
            max_delay=600.0,  # 10 minutes max delay
        )

        self.snapshot_retry_config = RetryConfig(
            max_attempts=5,  # More attempts for snapshots (faster operations)
            base_delay=1.0,
            max_delay=300.0,  # 5 minutes max delay
        )

    def get_retry_config_for_operation(self, operation_type: str) -> RetryConfig:
        """Get appropriate retry configuration based on operation type."""
        if "snapshot" in operation_type.lower():
            return self.snapshot_retry_config
        else:
            return self.backup_retry_config

    async def handle_backup_error(
        self,
        error: Exception,
        operation_result: OperationResult,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Handle backup-specific errors with operation result updates."""
        context = ErrorContext(
            operation=operation_result.operation.operation_type.value,
            resource_id=operation_result.operation.resource_id,
            resource_type=operation_result.operation.resource_type,
            resource_name=operation_result.operation.resource_name,
            additional_info=additional_context,
        )

        return await self.handle_error(error, context, operation_result)
