"""Custom logging formatters for structured and contextual logging."""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional, Union


class StructuredFormatter(logging.Formatter):
    """JSON-based structured logging formatter."""
    
    def __init__(
        self,
        include_context: bool = True,
        include_process_info: bool = True,
        timestamp_format: str = "iso",
    ):
        """Initialize structured formatter.
        
        Args:
            include_context: Whether to include extra context fields
            include_process_info: Whether to include process/thread info
            timestamp_format: Timestamp format ("iso", "epoch", "human")
        """
        super().__init__()
        self.include_context = include_context
        self.include_process_info = include_process_info
        self.timestamp_format = timestamp_format
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON-formatted log message
        """
        # Base log entry
        log_entry = {
            "timestamp": self._format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add process/thread information
        if self.include_process_info:
            log_entry.update({
                "process_id": os.getpid(),
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
            })
        
        # Add source location
        if record.pathname:
            log_entry.update({
                "file": os.path.basename(record.pathname),
                "line": record.lineno,
                "function": record.funcName,
            })
        
        # Add exception information
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None,
            }
        
        # Add extra context fields
        if self.include_context and hasattr(record, "__dict__"):
            # Get extra fields (excluding standard LogRecord attributes)
            standard_fields = {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "getMessage",
                "exc_info", "exc_text", "stack_info", "message"
            }
            
            extra_fields = {}
            for key, value in record.__dict__.items():
                if key not in standard_fields and not key.startswith("_"):
                    # Ensure value is JSON serializable
                    try:
                        json.dumps(value)
                        extra_fields[key] = value
                    except (TypeError, ValueError):
                        extra_fields[key] = str(value)
            
            if extra_fields:
                log_entry["context"] = extra_fields
        
        # Convert to JSON
        try:
            return json.dumps(log_entry, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as e:
            # Fallback to simple format if JSON serialization fails
            return f"JSON_SERIALIZATION_ERROR: {e} - Original message: {record.getMessage()}"
    
    def _format_timestamp(self, timestamp: float) -> Union[str, float]:
        """Format timestamp according to configuration.
        
        Args:
            timestamp: Unix timestamp
            
        Returns:
            Formatted timestamp
        """
        if self.timestamp_format == "epoch":
            return timestamp
        elif self.timestamp_format == "human":
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        else:  # iso
            return datetime.fromtimestamp(timestamp).isoformat()


class ContextFormatter(logging.Formatter):
    """Enhanced formatter that includes context information."""
    
    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        include_context: bool = True,
        context_separator: str = " | ",
    ):
        """Initialize context formatter.
        
        Args:
            fmt: Log format string
            datefmt: Date format string
            include_context: Whether to append context fields
            context_separator: Separator for context fields
        """
        if fmt is None:
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.include_context = include_context
        self.context_separator = context_separator
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with context information.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted log message with context
        """
        # Format base message
        formatted = super().format(record)
        
        # Add context if enabled
        if self.include_context:
            context_parts = self._extract_context(record)
            if context_parts:
                context_str = self.context_separator.join(context_parts)
                formatted = f"{formatted}{self.context_separator}{context_str}"
        
        return formatted
    
    def _extract_context(self, record: logging.LogRecord) -> list:
        """Extract context information from log record.
        
        Args:
            record: Log record
            
        Returns:
            List of context strings
        """
        context_parts = []
        
        # Standard context fields we want to include
        standard_fields = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "getMessage",
            "exc_info", "exc_text", "stack_info", "message"
        }
        
        # Extract extra fields
        for key, value in record.__dict__.items():
            if key not in standard_fields and not key.startswith("_"):
                # Format value appropriately
                if isinstance(value, (str, int, float, bool)):
                    context_parts.append(f"{key}={value}")
                elif isinstance(value, dict):
                    # Format dict as key-value pairs
                    dict_parts = [f"{k}={v}" for k, v in value.items()]
                    context_parts.append(f"{key}={{{','.join(dict_parts)}}}")
                else:
                    context_parts.append(f"{key}={str(value)}")
        
        return context_parts


class ColoredFormatter(logging.Formatter):
    """Formatter that adds color codes for console output."""
    
    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"
    
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        """Initialize colored formatter.
        
        Args:
            fmt: Log format string
            datefmt: Date format string
        """
        super().__init__(fmt=fmt, datefmt=datefmt)
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors.
        
        Args:
            record: Log record to format
            
        Returns:
            Colored log message
        """
        # Get color for log level
        color = self.COLORS.get(record.levelname, "")
        
        # Format message
        formatted = super().format(record)
        
        # Add color if available and output is a terminal
        if color and hasattr(os, "isatty") and os.isatty(2):  # stderr
            formatted = f"{color}{formatted}{self.RESET}"
        
        return formatted


class CompactFormatter(logging.Formatter):
    """Compact formatter for high-volume logging scenarios."""
    
    def __init__(self):
        """Initialize compact formatter."""
        super().__init__(
            fmt="%(asctime)s %(levelname).1s %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        )
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record in compact format.
        
        Args:
            record: Log record to format
            
        Returns:
            Compact log message
        """
        # Shorten logger name
        if "." in record.name:
            parts = record.name.split(".")
            if len(parts) > 2:
                record.name = f"{parts[0]}...{parts[-1]}"
        
        return super().format(record)