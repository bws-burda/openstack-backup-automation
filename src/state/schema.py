"""Database schema definitions and initialization."""

import sqlite3
from pathlib import Path
from typing import Optional


class DatabaseSchema:
    """Manages database schema creation and migrations."""

    # Current schema version
    SCHEMA_VERSION = 1

    # SQL statements for table creation
    CREATE_TABLES_SQL = [
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resources (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL CHECK (type IN ('instance', 'volume')),
            name TEXT,
            schedule_tag TEXT NOT NULL,
            last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active BOOLEAN DEFAULT TRUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_id TEXT NOT NULL UNIQUE,
            resource_id TEXT NOT NULL,
            resource_type TEXT NOT NULL CHECK (resource_type IN ('instance', 'volume')),
            backup_type TEXT NOT NULL CHECK (backup_type IN ('snapshot', 'full', 'incremental')),
            parent_backup_id TEXT,
            created_at TIMESTAMP NOT NULL,
            verified BOOLEAN DEFAULT FALSE,
            size_bytes INTEGER,
            schedule_tag TEXT NOT NULL,
            retention_days INTEGER,
            related_instance_snapshot_id TEXT,
            FOREIGN KEY (resource_id) REFERENCES resources (id),
            FOREIGN KEY (parent_backup_id) REFERENCES backups (backup_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backup_metadata (
            backup_id TEXT PRIMARY KEY,
            metadata_json TEXT,
            checksum TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (backup_id) REFERENCES backups (backup_id) ON DELETE CASCADE
        )
        """,
    ]

    # Indexes for performance
    CREATE_INDEXES_SQL = [
        "CREATE INDEX IF NOT EXISTS idx_backups_resource_id ON backups (resource_id)",
        "CREATE INDEX IF NOT EXISTS idx_backups_created_at ON backups (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_backups_backup_type ON backups (backup_type)",
        "CREATE INDEX IF NOT EXISTS idx_backups_parent_backup_id ON backups (parent_backup_id)",
        "CREATE INDEX IF NOT EXISTS idx_resources_type ON resources (type)",
        "CREATE INDEX IF NOT EXISTS idx_resources_active ON resources (active)",
        "CREATE INDEX IF NOT EXISTS idx_resources_last_scanned ON resources (last_scanned)",
    ]

    def __init__(self, db_path: str):
        """Initialize database schema manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def initialize_database(self) -> None:
        """Initialize database with schema and indexes."""
        with sqlite3.connect(self.db_path) as conn:
            # Enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON")

            # Create tables
            for sql in self.CREATE_TABLES_SQL:
                conn.execute(sql)

            # Create indexes
            for sql in self.CREATE_INDEXES_SQL:
                conn.execute(sql)

            # Set schema version
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (self.SCHEMA_VERSION,),
            )

            conn.commit()

    def get_current_version(self) -> Optional[int]:
        """Get current database schema version.

        Returns:
            Current schema version or None if not set
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return None

    def needs_migration(self) -> bool:
        """Check if database needs migration.

        Returns:
            True if migration is needed
        """
        current_version = self.get_current_version()
        return current_version is None or current_version < self.SCHEMA_VERSION

    def migrate_database(self) -> None:
        """Migrate database to current schema version."""
        current_version = self.get_current_version()

        if current_version is None:
            # Fresh database
            self.initialize_database()
            return

        if current_version < self.SCHEMA_VERSION:
            # No migrations needed - schema is created fresh
            pass

    def validate_database(self) -> bool:
        """Validate database schema integrity.

        Returns:
            True if database schema is valid
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Check if all required tables exist
                cursor = conn.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name IN ('resources', 'backups', 'backup_metadata', 'schema_version')
                """
                )
                tables = {row[0] for row in cursor.fetchall()}
                required_tables = {
                    "resources",
                    "backups",
                    "backup_metadata",
                    "schema_version",
                }

                if not required_tables.issubset(tables):
                    return False

                # Check schema version
                current_version = self.get_current_version()
                return current_version == self.SCHEMA_VERSION

        except sqlite3.Error:
            return False

    def get_database_stats(self) -> dict:
        """Get database statistics.

        Returns:
            Dictionary with database statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                stats = {}

                # Count resources
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM resources WHERE active = TRUE"
                )
                stats["active_resources"] = cursor.fetchone()[0]

                # Count backups by type
                cursor = conn.execute(
                    """
                    SELECT backup_type, COUNT(*)
                    FROM backups
                    GROUP BY backup_type
                """
                )
                backup_counts = dict(cursor.fetchall())
                stats["backup_counts"] = backup_counts

                # Total backups
                stats["total_backups"] = sum(backup_counts.values())

                # Database file size
                stats["db_size_bytes"] = (
                    self.db_path.stat().st_size if self.db_path.exists() else 0
                )

                return stats

        except sqlite3.Error as e:
            return {"error": str(e)}
