"""Logging configuration and setup utilities."""

import logging
import logging.handlers
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from .formatters import StructuredFormatter


@dataclass
class LoggingConfig:
    """Configuration for comprehensive logging setup."""

    # Basic configuration
    level: str = "INFO"

    # File logging
    log_file: Optional[str] = None
    max_file_size_mb: int = 10
    backup_count: int = 5

    # Console logging
    console_enabled: bool = True
    console_level: Optional[str] = None  # If None, uses main level

    # Structured logging options
    include_context: bool = True
    include_process_info: bool = True

    # Logger-specific levels
    logger_levels: Dict[str, str] = field(default_factory=dict)

    # Disable specific loggers (e.g., noisy third-party libraries)
    disabled_loggers: List[str] = field(
        default_factory=lambda: [
            "urllib3.connectionpool",
            "requests.packages.urllib3",
        ]
    )

    def __post_init__(self):
        """Validate logging configuration."""
        self._validate()

    def _validate(self):
        """Validate logging configuration parameters."""
        # Validate log levels
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        if self.level.upper() not in valid_levels:
            raise ValueError(
                f"Invalid log level: {self.level}. Must be one of: {valid_levels}"
            )

        if self.console_level and self.console_level.upper() not in valid_levels:
            raise ValueError(f"Invalid console log level: {self.console_level}")

        # Validate file size and backup count
        if self.max_file_size_mb <= 0:
            raise ValueError("Max file size must be positive")

        if self.backup_count < 0:
            raise ValueError("Backup count must be non-negative")

        # Validate logger levels
        for logger_name, level in self.logger_levels.items():
            if level.upper() not in valid_levels:
                raise ValueError(f"Invalid level '{level}' for logger '{logger_name}'")

        # Normalize levels to uppercase
        self.level = self.level.upper()
        if self.console_level:
            self.console_level = self.console_level.upper()

        self.logger_levels = {
            name: level.upper() for name, level in self.logger_levels.items()
        }


def setup_logging(config: LoggingConfig) -> None:
    """Set up comprehensive logging based on configuration.

    Args:
        config: Logging configuration object
    """
    # Clear any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set root logger level
    root_logger.setLevel(getattr(logging, config.level))

    # Create formatters
    formatter = _create_formatter(config)

    # Set up console handler
    if config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_level = config.console_level or config.level
        console_handler.setLevel(getattr(logging, console_level))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Set up file handler with rotation
    if config.log_file:
        file_handler = _create_file_handler(config, formatter)
        root_logger.addHandler(file_handler)

    # Configure specific logger levels
    for logger_name, level in config.logger_levels.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level))

    # Disable noisy loggers
    for logger_name in config.disabled_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)
        logger.propagate = False

    # Log the configuration
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "log_level": config.level,
            "console_enabled": config.console_enabled,
            "file_logging": bool(config.log_file),
        },
    )


def _create_formatter(config: LoggingConfig) -> logging.Formatter:
    """Create structured JSON formatter."""
    return StructuredFormatter(
        include_context=config.include_context,
        include_process_info=config.include_process_info,
    )


def _create_file_handler(
    config: LoggingConfig, formatter: logging.Formatter
) -> logging.Handler:
    """Create rotating file handler."""
    # Ensure log directory exists
    log_path = Path(config.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create rotating file handler
    max_bytes = config.max_file_size_mb * 1024 * 1024
    handler = logging.handlers.RotatingFileHandler(
        filename=config.log_file,
        maxBytes=max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )

    handler.setLevel(getattr(logging, config.level))
    handler.setFormatter(formatter)

    return handler


def get_logger(
    name: str, context: Optional[Dict[str, Union[str, int, float]]] = None
) -> logging.Logger:
    """Get a logger with optional context.

    Args:
        name: Logger name (usually __name__)
        context: Optional context dictionary to include in all log messages

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if context:
        # Create a logger adapter that adds context to all messages
        return ContextLoggerAdapter(logger, context)

    return logger


class ContextLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds context to all log messages."""

    def __init__(
        self, logger: logging.Logger, context: Dict[str, Union[str, int, float]]
    ):
        """Initialize adapter with context.

        Args:
            logger: Base logger instance
            context: Context dictionary to add to all messages
        """
        super().__init__(logger, context)

    def process(self, msg: str, kwargs: Dict) -> tuple:
        """Process log message and add context."""
        # Merge context with any extra data
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra

        return msg, kwargs


def configure_third_party_loggers():
    """Configure third-party library loggers to reduce noise."""
    # Reduce urllib3 verbosity
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    # Reduce requests verbosity
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("requests.packages.urllib3").setLevel(logging.WARNING)

    # Reduce OpenStack SDK verbosity
    logging.getLogger("openstack").setLevel(logging.WARNING)
    logging.getLogger("keystoneauth1").setLevel(logging.WARNING)

    # Reduce asyncio debug messages
    logging.getLogger("asyncio").setLevel(logging.WARNING)
