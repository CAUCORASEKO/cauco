from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

CURRENT_SCHEMA_VERSION = 6


class SQLitePersistenceError(RuntimeError):
    """Base error for Cauco SQLite persistence."""


class SQLiteSchemaVersionError(SQLitePersistenceError):
    """Raised when the database schema is newer than this Cauco build."""


class SQLiteDatabase:
    """Small SQLite foundation for local operational persistence.

    Each operation receives its own connection. SQLite WAL mode and a
    process-local initialization lock keep startup deterministic without
    sharing connection objects across application threads.
    """

    def __init__(
        self,
        path: Path,
        *,
        busy_timeout_ms: int = 5_000,
    ) -> None:
        if busy_timeout_ms < 100 or busy_timeout_ms > 60_000:
            raise ValueError("SQLite busy timeout must be between 100 and 60000 ms.")

        self.path = path.expanduser().resolve()
        self.busy_timeout_ms = busy_timeout_ms
        self._initialization_lock = RLock()

    def initialize(self) -> None:
        """Create or migrate the database to the supported schema version."""
        with self._initialization_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)

            try:
                with self.connection() as connection:
                    self._configure_database(connection)
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        self._create_schema_metadata(connection)
                        version = self._read_schema_version(connection)

                        if version > CURRENT_SCHEMA_VERSION:
                            raise SQLiteSchemaVersionError(
                                "SQLite schema version "
                                f"{version} is newer than supported version "
                                f"{CURRENT_SCHEMA_VERSION}."
                            )

                        if version < 1:
                            self._migrate_to_version_1(connection)
                            self._write_schema_version(connection, 1)
                            version = 1

                        if version < 2:
                            self._migrate_to_version_2(connection)
                            self._write_schema_version(connection, 2)
                            version = 2

                        if version < 3:
                            self._migrate_to_version_3(connection)
                            self._write_schema_version(connection, 3)
                            version = 3

                        if version < 4:
                            self._migrate_to_version_4(connection)
                            self._write_schema_version(connection, 4)
                            version = 4

                        if version < 5:
                            self._migrate_to_version_5(connection)
                            self._write_schema_version(connection, 5)
                            version = 5
                        if version < 6:
                            self._migrate_to_version_6(connection)
                            self._write_schema_version(connection, 6)

                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
            except SQLitePersistenceError:
                raise
            except sqlite3.Error as error:
                raise SQLitePersistenceError(
                    "Cauco could not initialize its local SQLite database."
                ) from error

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Open a configured SQLite connection and always close it."""
        connection: sqlite3.Connection | None = None

        try:
            connection = sqlite3.connect(
                self.path,
                timeout=self.busy_timeout_ms / 1000,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            self._configure_connection(connection)
            yield connection
        except sqlite3.Error as error:
            raise SQLitePersistenceError("Cauco SQLite operation failed safely.") from error
        finally:
            if connection is not None:
                connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run an atomic write transaction with automatic rollback."""
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def schema_version(self) -> int:
        """Return the initialized database schema version."""
        with self.connection() as connection:
            self._create_schema_metadata(connection)
            return self._read_schema_version(connection)

    def _configure_database(self, connection: sqlite3.Connection) -> None:
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "wal":
            raise SQLitePersistenceError("Cauco could not enable SQLite WAL mode.")

        connection.execute("PRAGMA synchronous=NORMAL")

    def _configure_connection(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")

        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
        if foreign_keys is None or int(foreign_keys[0]) != 1:
            raise SQLitePersistenceError("Cauco could not enable SQLite foreign keys.")

    @staticmethod
    def _create_schema_metadata(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY NOT NULL,
                value TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def _read_schema_version(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        ).fetchone()

        if row is None:
            return 0

        try:
            version = int(row["value"])
        except (TypeError, ValueError) as error:
            raise SQLiteSchemaVersionError("SQLite schema version metadata is invalid.") from error

        if version < 0:
            raise SQLiteSchemaVersionError("SQLite schema version metadata is invalid.")

        return version

    @staticmethod
    def _write_schema_version(
        connection: sqlite3.Connection,
        version: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(version),),
        )

    @staticmethod
    def _migrate_to_version_2(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_write_proposals (
                proposal_id TEXT PRIMARY KEY NOT NULL,
                proposal_json TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                applied_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_memory_write_proposals_state
                ON memory_write_proposals(state);

            CREATE INDEX IF NOT EXISTS idx_memory_write_proposals_expires_at
                ON memory_write_proposals(expires_at);
            """
        )

    @staticmethod
    def _migrate_to_version_3(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_plan_reviews (
                review_id TEXT PRIMARY KEY NOT NULL,
                record_json TEXT NOT NULL,
                status TEXT NOT NULL,
                selected_agent_id TEXT NOT NULL,
                snapshot_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_plan_reviews_status
                ON agent_plan_reviews(status);

            CREATE INDEX IF NOT EXISTS idx_agent_plan_reviews_agent
                ON agent_plan_reviews(selected_agent_id);

            CREATE INDEX IF NOT EXISTS idx_agent_plan_reviews_created_at
                ON agent_plan_reviews(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_agent_plan_reviews_expires_at
                ON agent_plan_reviews(expires_at);

            """
        )

    @staticmethod
    def _migrate_to_version_4(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS verification_records (
                verification_id TEXT PRIMARY KEY NOT NULL,
                execution_id TEXT NOT NULL UNIQUE,
                review_id TEXT NOT NULL,
                snapshot_digest TEXT NOT NULL,
                outcome TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                record_json TEXT NOT NULL,
                FOREIGN KEY (execution_id)
                    REFERENCES executions(execution_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_verification_records_review
                ON verification_records(review_id);

            CREATE INDEX IF NOT EXISTS idx_verification_records_outcome
                ON verification_records(outcome);

            CREATE INDEX IF NOT EXISTS idx_verification_records_created_at
                ON verification_records(created_at DESC);
            """
        )

    @staticmethod
    def _migrate_to_version_5(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS experience_records (
                experience_id TEXT PRIMARY KEY NOT NULL,
                verification_id TEXT NOT NULL UNIQUE,
                execution_id TEXT NOT NULL,
                review_id TEXT NOT NULL,
                snapshot_digest TEXT NOT NULL,
                outcome TEXT NOT NULL,
                memory_candidate INTEGER NOT NULL,
                method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                record_json TEXT NOT NULL,
                FOREIGN KEY (verification_id)
                    REFERENCES verification_records(verification_id)
                    ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_experience_records_review
                ON experience_records(review_id);
            CREATE INDEX IF NOT EXISTS idx_experience_records_outcome
                ON experience_records(outcome);
            CREATE INDEX IF NOT EXISTS idx_experience_records_memory_candidate
                ON experience_records(memory_candidate);
            CREATE INDEX IF NOT EXISTS idx_experience_records_created_at
                ON experience_records(created_at DESC);
            """
        )

    @staticmethod
    def _migrate_to_version_6(connection: sqlite3.Connection) -> None:
        # ruff: noqa: E501
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS memory_candidates (
            candidate_id TEXT PRIMARY KEY NOT NULL, experience_id TEXT NOT NULL,
            verification_id TEXT NOT NULL, execution_id TEXT NOT NULL, review_id TEXT NOT NULL,
            snapshot_digest TEXT NOT NULL, category TEXT NOT NULL, target TEXT NOT NULL,
            status TEXT NOT NULL, disposition TEXT, confidence REAL NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL, reviewed_at TEXT,
            record_json TEXT NOT NULL,
            FOREIGN KEY (experience_id) REFERENCES experience_records(experience_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_memory_candidates_experience ON memory_candidates(experience_id);
        CREATE INDEX IF NOT EXISTS idx_memory_candidates_review ON memory_candidates(review_id);
        CREATE INDEX IF NOT EXISTS idx_memory_candidates_status ON memory_candidates(status);
        CREATE INDEX IF NOT EXISTS idx_memory_candidates_target ON memory_candidates(target);
        CREATE INDEX IF NOT EXISTS idx_memory_candidates_created_at ON memory_candidates(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_memory_candidates_expires_at ON memory_candidates(expires_at);
        """)

    @staticmethod
    def _migrate_to_version_1(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY NOT NULL,
                review_id TEXT NOT NULL UNIQUE,
                snapshot_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                current_step_index INTEGER,
                total_steps INTEGER NOT NULL,
                execution_performed INTEGER NOT NULL DEFAULT 0,
                failure_reason TEXT,
                warning TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_executions_created_at
                ON executions(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_executions_status
                ON executions(status);

            CREATE TABLE IF NOT EXISTS execution_steps (
                execution_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                tool_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                target TEXT,
                status TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                result_json TEXT,
                error TEXT,
                execution_performed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (execution_id, step_index),
                FOREIGN KEY (execution_id)
                    REFERENCES executions(execution_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS execution_audit_events (
                event_id TEXT PRIMARY KEY NOT NULL,
                execution_id TEXT,
                review_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                step_index INTEGER,
                tool_id TEXT,
                operation_id TEXT,
                outcome TEXT NOT NULL,
                safe_message TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (execution_id)
                    REFERENCES executions(execution_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_execution_audit_timestamp
                ON execution_audit_events(timestamp DESC);

            CREATE INDEX IF NOT EXISTS idx_execution_audit_execution
                ON execution_audit_events(execution_id);

            CREATE TABLE IF NOT EXISTS rejected_execution_audit_events (
                event_id TEXT PRIMARY KEY NOT NULL,
                review_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                outcome TEXT NOT NULL,
                safe_message TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS mutation_previews (
                preview_id TEXT PRIMARY KEY NOT NULL,
                execution_id TEXT NOT NULL,
                review_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                tool_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                target TEXT,
                normalized_arguments_json TEXT NOT NULL,
                before_state_json TEXT NOT NULL,
                proposed_after_state_json TEXT NOT NULL,
                diff_preview TEXT NOT NULL,
                preview_digest TEXT NOT NULL,
                confirmation_phrase TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL,
                warning TEXT NOT NULL,
                FOREIGN KEY (execution_id)
                    REFERENCES executions(execution_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_mutation_previews_step
                ON mutation_previews(execution_id, step_index);

            CREATE INDEX IF NOT EXISTS idx_mutation_previews_status
                ON mutation_previews(status);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_mutation_active_step
                ON mutation_previews(execution_id, step_index)
                WHERE status IN ('pending_confirmation', 'confirmed');
            """
        )
