"""State manager for backup history and metadata tracking."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from ..backup.models import BackupInfo, BackupType
from ..interfaces import StateManagerInterface
from .schema import DatabaseSchema


class StateManager(StateManagerInterface):
    """Manages backup state and history using SQLite database."""

    def __init__(self, db_path: str = "backup_state.db"):
        """Initialize state manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.schema = DatabaseSchema(str(self.db_path))
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Initialize database if needed."""
        if self.schema.needs_migration():
            self.schema.migrate_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with proper configuration."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    def record_backup(self, backup_info: BackupInfo) -> None:
        """Record a completed backup in the database.

        Args:
            backup_info: Information about the completed backup
        """
        with self._get_connection() as conn:
            # First, ensure resource exists
            conn.execute(
                """
                INSERT OR REPLACE INTO resources (id, type, schedule_tag, last_scanned)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    backup_info.resource_id,
                    backup_info.resource_type,
                    backup_info.schedule_tag or "",
                ),
            )

            # Record the backup
            conn.execute(
                """
                INSERT INTO backups (
                    backup_id, resource_id, resource_type, backup_type,
                    parent_backup_id, created_at, verified, size_bytes, schedule_tag, retention_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    backup_info.backup_id,
                    backup_info.resource_id,
                    backup_info.resource_type,
                    backup_info.backup_type.value,
                    backup_info.parent_backup_id,
                    backup_info.created_at or datetime.now(timezone.utc),
                    backup_info.verified,
                    backup_info.size_bytes,
                    backup_info.schedule_tag or "",
                    backup_info.retention_days,
                ),
            )

            conn.commit()

    def get_last_backup(self, resource_id: str) -> Optional[BackupInfo]:
        """Get the most recent backup for a resource.

        Args:
            resource_id: ID of the resource

        Returns:
            Most recent backup info or None if no backups exist
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT backup_id, resource_id, resource_type, backup_type,
                       parent_backup_id, created_at, verified, size_bytes, schedule_tag
                FROM backups
                WHERE resource_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (resource_id,),
            )

            row = cursor.fetchone()
            if row:
                return self._row_to_backup_info(row)
            return None

    def get_backup_chain(self, resource_id: str) -> List[BackupInfo]:
        """Get the complete backup chain for a resource.

        Args:
            resource_id: ID of the resource

        Returns:
            List of backup info ordered by creation time (oldest first)
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT backup_id, resource_id, resource_type, backup_type,
                       parent_backup_id, created_at, verified, size_bytes, schedule_tag
                FROM backups
                WHERE resource_id = ?
                ORDER BY created_at ASC
            """,
                (resource_id,),
            )

            return [self._row_to_backup_info(row) for row in cursor.fetchall()]

    def get_backups_older_than(self, days: int) -> List[BackupInfo]:
        """Get backups older than specified number of days.

        Args:
            days: Number of days threshold

        Returns:
            List of backup info for old backups
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT backup_id, resource_id, resource_type, backup_type,
                       parent_backup_id, created_at, verified, size_bytes, schedule_tag
                FROM backups
                WHERE created_at < ?
                ORDER BY created_at ASC
            """,
                (cutoff_date,),
            )

            return [self._row_to_backup_info(row) for row in cursor.fetchall()]

    def get_dependent_incrementals(self, full_backup_id: str) -> List[BackupInfo]:
        """Get all incremental backups that depend on a full backup.

        Args:
            full_backup_id: ID of the full backup

        Returns:
            List of dependent incremental backups
        """
        with self._get_connection() as conn:
            # Get all backups that have this full backup in their chain
            cursor = conn.execute(
                """
                WITH RECURSIVE backup_chain AS (
                    -- Start with direct children
                    SELECT backup_id, resource_id, resource_type, backup_type,
                           parent_backup_id, created_at, verified, size_bytes, schedule_tag
                    FROM backups
                    WHERE parent_backup_id = ?

                    UNION ALL

                    -- Recursively find children of children
                    SELECT b.backup_id, b.resource_id, b.resource_type, b.backup_type,
                           b.parent_backup_id, b.created_at, b.verified, b.size_bytes, b.schedule_tag
                    FROM backups b
                    INNER JOIN backup_chain bc ON b.parent_backup_id = bc.backup_id
                )
                SELECT * FROM backup_chain
                ORDER BY created_at ASC
            """,
                (full_backup_id,),
            )

            return [self._row_to_backup_info(row) for row in cursor.fetchall()]

    def delete_backup_record(self, backup_id: str) -> None:
        """Delete a backup record from the database.

        Args:
            backup_id: ID of the backup to delete
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM backups WHERE backup_id = ?", (backup_id,))
            conn.commit()

    def update_resource_status(
        self, resource_id: str, last_backup: datetime, active: bool = True
    ) -> None:
        """Update resource status and last backup time.

        Args:
            resource_id: ID of the resource
            last_backup: Timestamp of last backup
            active: Whether resource is still active
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE resources
                SET last_scanned = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (resource_id,),
            )
            conn.commit()

    def get_backup_by_id(self, backup_id: str) -> Optional[BackupInfo]:
        """Get backup information by backup ID.

        Args:
            backup_id: ID of the backup

        Returns:
            Backup info or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT backup_id, resource_id, resource_type, backup_type,
                       parent_backup_id, created_at, verified, size_bytes, schedule_tag
                FROM backups
                WHERE backup_id = ?
            """,
                (backup_id,),
            )

            row = cursor.fetchone()
            if row:
                return self._row_to_backup_info(row)
            return None

    def get_last_full_backup(self, resource_id: str) -> Optional[BackupInfo]:
        """Get the most recent full backup for a resource.

        Args:
            resource_id: ID of the resource

        Returns:
            Most recent full backup info or None if no full backups exist
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT backup_id, resource_id, resource_type, backup_type,
                       parent_backup_id, created_at, verified, size_bytes, schedule_tag
                FROM backups
                WHERE resource_id = ? AND backup_type = 'full'
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (resource_id,),
            )

            row = cursor.fetchone()
            if row:
                return self._row_to_backup_info(row)
            return None

    def get_incremental_backups_since(
        self, resource_id: str, since_backup_id: str
    ) -> List[BackupInfo]:
        """Get incremental backups created after a specific backup.

        Args:
            resource_id: ID of the resource
            since_backup_id: ID of the reference backup

        Returns:
            List of incremental backups created after the reference backup
        """
        # First get the reference backup's timestamp
        reference_backup = self.get_backup_by_id(since_backup_id)
        if not reference_backup:
            return []

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT backup_id, resource_id, resource_type, backup_type,
                       parent_backup_id, created_at, verified, size_bytes, schedule_tag
                FROM backups
                WHERE resource_id = ?
                  AND backup_type = 'incremental'
                  AND created_at > ?
                ORDER BY created_at ASC
            """,
                (resource_id, reference_backup.created_at),
            )

            return [self._row_to_backup_info(row) for row in cursor.fetchall()]

    def mark_backup_verified(self, backup_id: str, verified: bool = True) -> None:
        """Mark a backup as verified or unverified.

        Args:
            backup_id: ID of the backup
            verified: Whether the backup is verified
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE backups
                SET verified = ?
                WHERE backup_id = ?
            """,
                (verified, backup_id),
            )
            conn.commit()

    def get_backup_statistics(self) -> dict:
        """Get backup statistics.

        Returns:
            Dictionary with backup statistics
        """
        with self._get_connection() as conn:
            stats = {}

            # Total backups by type
            cursor = conn.execute(
                """
                SELECT backup_type, COUNT(*) as count
                FROM backups
                GROUP BY backup_type
            """
            )
            stats["backup_counts"] = dict(cursor.fetchall())

            # Verified vs unverified
            cursor = conn.execute(
                """
                SELECT verified, COUNT(*) as count
                FROM backups
                GROUP BY verified
            """
            )
            verification_stats = dict(cursor.fetchall())
            stats["verified_backups"] = verification_stats.get(
                1, 0
            )  # SQLite uses 1 for True
            stats["unverified_backups"] = verification_stats.get(
                0, 0
            )  # SQLite uses 0 for False

            # Total storage used (if size information is available)
            cursor = conn.execute(
                "SELECT SUM(size_bytes) FROM backups WHERE size_bytes IS NOT NULL"
            )
            total_size = cursor.fetchone()[0]
            stats["total_size_bytes"] = total_size or 0

            # Active resources
            cursor = conn.execute("SELECT COUNT(*) FROM resources WHERE active = TRUE")
            stats["active_resources"] = cursor.fetchone()[0]

            return stats

    def cleanup_old_records(self, retention_days: int) -> int:
        """Clean up old backup records from database.

        Args:
            retention_days: Number of days to retain records

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM backups
                WHERE created_at < ?
            """,
                (cutoff_date,),
            )

            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

    def _row_to_backup_info(self, row: sqlite3.Row) -> BackupInfo:
        """Convert database row to BackupInfo object.

        Args:
            row: Database row

        Returns:
            BackupInfo object
        """
        return BackupInfo(
            backup_id=row["backup_id"],
            resource_id=row["resource_id"],
            resource_type=row["resource_type"],
            backup_type=BackupType(row["backup_type"]),
            parent_backup_id=row["parent_backup_id"],
            created_at=(
                datetime.fromisoformat(row["created_at"]) if row["created_at"] else None
            ),
            verified=bool(row["verified"]),
            size_bytes=row["size_bytes"],
            schedule_tag=row["schedule_tag"],
        )
