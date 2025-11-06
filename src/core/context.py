"""Backup execution context for test mode and dry run support."""

from dataclasses import dataclass


@dataclass
class BackupContext:
    """Context for backup execution with test mode and dry run support.

    This class encapsulates the execution context for backup operations,
    allowing for different modes of operation:
    - Normal mode: Standard production execution
    - Test mode: Ignores timing constraints for testing
    - Dry run: Simulates operations without executing them
    - Combined: Test mode + dry run for safe testing
    """

    test_mode: bool = False
    """If True, ignore timing constraints and execute all policies."""

    dry_run: bool = False
    """If True, simulate operations without actually executing them."""

    def should_ignore_timing(self) -> bool:
        """Check if timing constraints should be ignored.

        Returns:
            True if in test mode, False otherwise.
        """
        return self.test_mode

    def should_simulate_operations(self) -> bool:
        """Check if operations should be simulated instead of executed.

        Returns:
            True if in dry run mode, False otherwise.
        """
        return self.dry_run

    def get_mode_description(self) -> str:
        """Get a human-readable description of the current mode.

        Returns:
            String describing the current execution mode.
        """
        if self.test_mode and self.dry_run:
            return "Test Mode + Dry Run (ignore timing, simulate operations)"
        elif self.test_mode:
            return "Test Mode (ignore timing, execute operations)"
        elif self.dry_run:
            return "Dry Run (respect timing, simulate operations)"
        else:
            return "Normal Mode (respect timing, execute operations)"
