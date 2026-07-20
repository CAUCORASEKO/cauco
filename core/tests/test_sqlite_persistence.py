import sqlite3
from pathlib import Path

import pytest

from cauco_core.persistence import (
    CURRENT_SCHEMA_VERSION,
    SQLiteDatabase,
    SQLiteSchemaVersionError,
)


def test_initialize_creates_versioned_database(tmp_path: Path) -> None:
    path = tmp_path / "state" / "cauco.db"
    database = SQLiteDatabase(path)

    database.initialize()

    assert path.is_file()
    assert database.schema_version() == CURRENT_SCHEMA_VERSION


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")

    database.initialize()
    database.initialize()

    assert database.schema_version() == CURRENT_SCHEMA_VERSION


def test_initialize_creates_phase_8_tables(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    database.initialize()

    with database.connection() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

    assert {
        "schema_metadata",
        "executions",
        "execution_steps",
        "execution_audit_events",
        "rejected_execution_audit_events",
        "mutation_previews",
        "memory_write_proposals",
    } <= names


def test_version_1_database_is_migrated_to_current_version(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    database = SQLiteDatabase(path)
    database.initialize()

    with database.transaction() as connection:
        connection.execute("DROP TABLE memory_write_proposals")
        connection.execute(
            """
            UPDATE schema_metadata
            SET value = '1'
            WHERE key = 'schema_version'
            """
        )

    database.initialize()

    assert database.schema_version() == CURRENT_SCHEMA_VERSION

    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'memory_write_proposals'
            """
        ).fetchone()

    assert row is not None


def test_connection_enables_foreign_keys_and_wal(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    database.initialize()

    with database.connection() as connection:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert foreign_keys == 1
    assert str(journal_mode).lower() == "wal"


def test_transaction_commits_successfully(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    database.initialize()

    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO schema_metadata (key, value)
            VALUES ('test_key', 'committed')
            """
        )

    with database.connection() as connection:
        value = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'test_key'"
        ).fetchone()["value"]

    assert value == "committed"


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    database.initialize()

    with pytest.raises(RuntimeError, match="stop"), database.transaction() as connection:
        connection.execute(
            """
                INSERT INTO schema_metadata (key, value)
                VALUES ('test_key', 'not-committed')
                """
        )
        raise RuntimeError("stop")

    with database.connection() as connection:
        row = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'test_key'"
        ).fetchone()

    assert row is None


def test_newer_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"

    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE schema_metadata (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO schema_metadata (key, value)
        VALUES ('schema_version', ?)
        """,
        (str(CURRENT_SCHEMA_VERSION + 1),),
    )
    connection.commit()
    connection.close()

    database = SQLiteDatabase(path)

    with pytest.raises(SQLiteSchemaVersionError, match="newer than supported"):
        database.initialize()


def test_invalid_busy_timeout_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy timeout"):
        SQLiteDatabase(tmp_path / "cauco.db", busy_timeout_ms=99)
