"""Daemon mode scheduler with internal scheduling."""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .coordinator import ExecutionCoordinator


class DaemonScheduler:
    """Daemon scheduler that runs backup cycles at regular intervals."""

    def __init__(self, coordinator: ExecutionCoordinator, check_interval_minutes: int = 15):
        """Initialize the daemon scheduler.
        
        Args:
            coordinator: Execution coordinator for backup operations
            check_interval_minutes: Interval between backup cycle checks
        """
        self.coordinator = coordinator
        self.check_interval_minutes = check_interval_minutes
        self.check_interval_seconds = check_interval_minutes * 60
        self.logger = logging.getLogger(__name__)
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._current_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the daemon scheduler."""
        if self._running:
            self.logger.warning("Daemon scheduler is already running")
            return

        self.logger.info(f"Starting daemon scheduler with {self.check_interval_minutes}-minute intervals")
        self._running = True
        self._shutdown_event.clear()

        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()

        try:
            await self._run_scheduler_loop()
        except asyncio.CancelledError:
            self.logger.info("Daemon scheduler was cancelled")
        except Exception as e:
            self.logger.error(f"Daemon scheduler failed: {e}", exc_info=True)
        finally:
            self._running = False
            self.logger.info("Daemon scheduler stopped")

    async def stop(self) -> None:
        """Stop the daemon scheduler gracefully."""
        if not self._running:
            self.logger.info("Daemon scheduler is not running")
            return

        self.logger.info("Stopping daemon scheduler...")
        self._running = False
        self._shutdown_event.set()

        # Cancel current task if running
        if self._current_task and not self._current_task.done():
            self.logger.info("Cancelling current backup cycle...")
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.stop())

        # Handle SIGTERM and SIGINT for graceful shutdown
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    async def _run_scheduler_loop(self) -> None:
        """Main scheduler loop that runs backup cycles at intervals."""
        self.logger.info("Daemon scheduler loop started")
        
        # Run initial backup cycle
        await self._execute_backup_cycle()

        while self._running and not self._shutdown_event.is_set():
            try:
                # Wait for the next interval or shutdown signal
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.check_interval_seconds
                )
                # If we get here, shutdown was requested
                break
            except asyncio.TimeoutError:
                # Timeout is expected - time for next backup cycle
                if self._running:
                    await self._execute_backup_cycle()

    async def _execute_backup_cycle(self) -> None:
        """Execute a backup cycle and handle any errors."""
        cycle_start = datetime.now(timezone.utc)
        self.logger.info(f"Starting scheduled backup cycle at {cycle_start}")

        try:
            # Create task for the backup cycle
            self._current_task = asyncio.create_task(
                self.coordinator.execute_backup_cycle(dry_run=False)
            )
            
            # Execute the backup cycle
            results = await self._current_task
            
            # Log summary
            duration = results.get("duration_seconds", 0)
            successful = results.get("successful_operations", 0)
            failed = results.get("failed_operations", 0)
            deleted = results.get("retention_deleted", 0)
            
            self.logger.info(
                f"Backup cycle completed in {duration:.1f}s: "
                f"{successful} successful, {failed} failed, {deleted} cleaned up"
            )

        except asyncio.CancelledError:
            self.logger.info("Backup cycle was cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Backup cycle failed: {e}", exc_info=True)
        finally:
            self._current_task = None

    async def get_status(self) -> Dict[str, Any]:
        """Get current daemon status."""
        status = {
            "running": self._running,
            "check_interval_minutes": self.check_interval_minutes,
            "timestamp": datetime.now(timezone.utc),
        }

        if self._current_task:
            status["current_task"] = {
                "running": not self._current_task.done(),
                "cancelled": self._current_task.cancelled(),
            }

        # Get system status from coordinator
        try:
            system_status = await self.coordinator.get_system_status()
            status["system"] = system_status
        except Exception as e:
            status["system_error"] = str(e)

        return status

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check of the daemon and underlying systems."""
        health = {
            "daemon_status": "healthy" if self._running else "stopped",
            "timestamp": datetime.now(timezone.utc),
        }

        try:
            # Get system health from coordinator
            system_health = await self.coordinator.validate_system_health()
            health.update(system_health)
        except Exception as e:
            health["daemon_status"] = "unhealthy"
            health["error"] = str(e)

        return health


class DaemonRunner:
    """High-level daemon runner that manages the complete daemon lifecycle."""

    def __init__(self, coordinator: ExecutionCoordinator, check_interval_minutes: int = 15):
        """Initialize the daemon runner.
        
        Args:
            coordinator: Execution coordinator for backup operations
            check_interval_minutes: Interval between backup cycle checks
        """
        self.scheduler = DaemonScheduler(coordinator, check_interval_minutes)
        self.logger = logging.getLogger(__name__)

    async def run(self) -> int:
        """Run the daemon and return exit code."""
        try:
            self.logger.info("Starting OpenStack Backup Automation daemon")
            await self.scheduler.start()
            return 0
        except KeyboardInterrupt:
            self.logger.info("Daemon interrupted by user")
            return 0
        except Exception as e:
            self.logger.error(f"Daemon failed: {e}", exc_info=True)
            return 1
        finally:
            await self.scheduler.stop()

    def run_sync(self) -> int:
        """Synchronous wrapper for running the daemon."""
        try:
            return asyncio.run(self.run())
        except KeyboardInterrupt:
            self.logger.info("Daemon interrupted")
            return 0
        except Exception as e:
            self.logger.error(f"Failed to start daemon: {e}", exc_info=True)
            return 1