"""The state database's schema, as an ordered list applied at agent startup.

Each entry is applied exactly once, in order, and the version it produces is
recorded as soon as it finishes. Every step is written so that re-running it is
harmless: the first agents shipped without a `schema_version` table at all, so
their databases arrive here looking like version 0 with the tables already in
place.
"""
from __future__ import annotations

import sqlite3


class SchemaTooNew(RuntimeError):
    """The database was written by a newer agent than this one."""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    # ALTER TABLE has no IF NOT EXISTS, and the column may already be there:
    # state.py created it directly before this module existed.
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _v1_projects(conn: sqlite3.Connection) -> None:
    # One statement per execute(), not executescript(): that commits any open
    # transaction first, which would break the one migrate() holds.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            guest_path TEXT NOT NULL,
            domain TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'stopped'
        )""")


def _v2_project_problem(conn: sqlite3.Connection) -> None:
    _add_column(conn, "projects", "problem_code", "TEXT")
    _add_column(conn, "projects", "problem_message", "TEXT")


# Append only. Editing an entry that has already shipped changes nothing on a
# database that ran it -- add the next one instead.
MIGRATIONS = [
    _v1_projects,
    _v2_project_problem,
]
SCHEMA_VERSION = len(MIGRATIONS)


def _read_version(conn: sqlite3.Connection) -> int:
    """Reads without writing: nothing may touch a database until the too-new
    check has passed on it."""
    known = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                         "AND name='schema_version'").fetchone()
    if not known:
        return 0
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return int(row[0]) if row else 0


def _write_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))


def migrate(conn: sqlite3.Connection) -> int:
    """Brings `conn` to `SCHEMA_VERSION` and returns it. Raises `SchemaTooNew`
    without touching anything if the database is ahead of this agent."""
    version = _read_version(conn)
    if version > SCHEMA_VERSION:
        raise SchemaTooNew(
            f"the state database is at schema version {version}, but this "
            f"agent only knows version {SCHEMA_VERSION}. It was written by a "
            f"newer agent; run the newer one, or delete the database — the "
            f"project list is rebuilt from the projects directory.")
    if version == SCHEMA_VERSION:
        return version
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version "
                 "(version INTEGER NOT NULL)")
    conn.commit()
    for index in range(version, SCHEMA_VERSION):
        # A step and the version marker recording it are one transaction. Every
        # step today is idempotent, but the first backfill anyone adds must not
        # be able to run twice after a crash between the two.
        conn.execute("BEGIN")
        try:
            MIGRATIONS[index](conn)
            _write_version(conn, index + 1)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return SCHEMA_VERSION
