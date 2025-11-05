"""Custom logging handlers for specialized logging needs."""

import logging
import logging.handlers
import socket
import time
from pathlib import Path
from typing import Optional


class RotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Enhanced rotating file handler with better error handling."""

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False,
        create_dirs: bool = True,
    ):
        """Initialize enhanced rotating file handler.

        Args:
            filename: Log file path
            mode: File open mode
            maxBytes: Maximum file size before rotation
            backupCount: Number of backup files to keep
            encoding: File encoding
            delay: Whether to delay file opening
            create_dirs: Whether to create parent directories
        """
        if create_dirs:
            # Ensure parent directory exists
            log_path = Path(filename)
            log_path.parent.mkdir(parents=True, exist_ok=True)

        super().__init__(
            filename=filename,
            mode=mode,
            maxBytes=maxBytes,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
        )

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record with enhanced error handling.

        Args:
            record: Log record to emit
        """
        try:
            super().emit(record)
        except (OSError, IOError):
            # Handle file system errors gracefully
            self.handleError(record)

            # Try to recreate the file handler
            try:
                if self.stream:
                    self.stream.close()
                    self.stream = None

                # Reopen the file
                self.stream = self._open()
                super().emit(record)
            except Exception:
                # If we still can't write, give up for this record
                pass

    def doRollover(self) -> None:
        """Perform log rotation with enhanced error handling."""
        try:
            super().doRollover()
        except (OSError, IOError):
            # Handle rotation errors (e.g., permission issues)
            self.handleError(None)


class SyslogHandler(logging.handlers.SysLogHandler):
    """Enhanced syslog handler with better connection management."""

    def __init__(
        self,
        address: tuple = ("localhost", 514),
        facility: int = logging.handlers.SysLogHandler.LOG_USER,
        socktype: int = socket.SOCK_DGRAM,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
    ):
        """Initialize enhanced syslog handler.

        Args:
            address: Syslog server address
            facility: Syslog facility
            socktype: Socket type
            retry_attempts: Number of retry attempts on failure
            retry_delay: Delay between retry attempts
        """
        super().__init__(address=address, facility=facility, socktype=socktype)
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record with retry logic.

        Args:
            record: Log record to emit
        """
        for attempt in range(self.retry_attempts):
            try:
                super().emit(record)
                return
            except Exception:
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay)
                    # Try to reconnect
                    try:
                        self.close()
                        self.socket = None
                    except Exception:
                        pass
                else:
                    # Final attempt failed
                    self.handleError(record)


class BufferedHandler(logging.Handler):
    """Buffered handler that flushes logs in batches."""

    def __init__(
        self,
        target_handler: logging.Handler,
        buffer_size: int = 100,
        flush_interval: float = 30.0,
    ):
        """Initialize buffered handler.

        Args:
            target_handler: Handler to buffer for
            buffer_size: Number of records to buffer before flushing
            flush_interval: Maximum time between flushes (seconds)
        """
        super().__init__()
        self.target_handler = target_handler
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.buffer = []
        self.last_flush = time.time()

    def emit(self, record: logging.LogRecord) -> None:
        """Add record to buffer and flush if necessary.

        Args:
            record: Log record to buffer
        """
        self.buffer.append(record)

        # Check if we should flush
        current_time = time.time()
        should_flush = (
            len(self.buffer) >= self.buffer_size
            or (current_time - self.last_flush) >= self.flush_interval
        )

        if should_flush:
            self.flush()

    def flush(self) -> None:
        """Flush buffered records to target handler."""
        if not self.buffer:
            return

        try:
            for record in self.buffer:
                self.target_handler.emit(record)

            self.target_handler.flush()
            self.buffer.clear()
            self.last_flush = time.time()

        except Exception:
            self.handleError(None)

    def close(self) -> None:
        """Close handler and flush remaining records."""
        self.flush()
        self.target_handler.close()
        super().close()


class AsyncHandler(logging.Handler):
    """Asynchronous handler that processes logs in a separate thread."""

    def __init__(
        self,
        target_handler: logging.Handler,
        queue_size: int = 1000,
    ):
        """Initialize async handler.

        Args:
            target_handler: Handler to process logs asynchronously
            queue_size: Maximum queue size
        """
        super().__init__()
        self.target_handler = target_handler

        try:
            import queue
            import threading

            self.queue = queue.Queue(maxsize=queue_size)
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            self._async_available = True
        except ImportError:
            # Fallback to synchronous operation
            self._async_available = False

    def emit(self, record: logging.LogRecord) -> None:
        """Add record to async queue or process synchronously.

        Args:
            record: Log record to process
        """
        if self._async_available:
            try:
                self.queue.put_nowait(record)
            except Exception:
                # Queue full, process synchronously as fallback
                self.target_handler.emit(record)
        else:
            # No async support, process synchronously
            self.target_handler.emit(record)

    def _worker(self) -> None:
        """Worker thread that processes queued log records."""
        while True:
            try:
                record = self.queue.get()
                if record is None:  # Shutdown signal
                    break

                self.target_handler.emit(record)
                self.queue.task_done()

            except Exception:
                # Handle errors in worker thread
                self.handleError(None)

    def close(self) -> None:
        """Close async handler and stop worker thread."""
        if self._async_available:
            # Signal worker thread to stop
            self.queue.put(None)
            self.thread.join(timeout=5.0)

        self.target_handler.close()
        super().close()


class MetricsHandler(logging.Handler):
    """Handler that collects logging metrics."""

    def __init__(self):
        """Initialize metrics handler."""
        super().__init__()
        self.metrics = {
            "total_records": 0,
            "records_by_level": {},
            "records_by_logger": {},
            "errors": 0,
        }

    def emit(self, record: logging.LogRecord) -> None:
        """Collect metrics from log record.

        Args:
            record: Log record to analyze
        """
        self.metrics["total_records"] += 1

        # Count by level
        level = record.levelname
        self.metrics["records_by_level"][level] = (
            self.metrics["records_by_level"].get(level, 0) + 1
        )

        # Count by logger
        logger_name = record.name
        self.metrics["records_by_logger"][logger_name] = (
            self.metrics["records_by_logger"].get(logger_name, 0) + 1
        )

        # Count errors
        if record.levelno >= logging.ERROR:
            self.metrics["errors"] += 1

    def get_metrics(self) -> dict:
        """Get collected metrics.

        Returns:
            Dictionary of collected metrics
        """
        return self.metrics.copy()

    def reset_metrics(self) -> None:
        """Reset collected metrics."""
        self.metrics = {
            "total_records": 0,
            "records_by_level": {},
            "records_by_logger": {},
            "errors": 0,
        }
