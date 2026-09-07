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


def _v1_projects_and_forwards(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            guest_path TEXT NOT NULL,
            domain TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'stopped'
        );
        CREATE TABLE IF NOT EXISTS forwards (
            project_id TEXT NOT NULL,
            service TEXT NOT NULL,
            guest_port INTEGER NOT NULL,
            host_port INTEGER NOT NULL UNIQUE
        );
    """)


def _v2_project_problem(conn: sqlite3.Connection) -> None:
    _add_column(conn, "projects", "problem_code", "TEXT")
    _add_column(conn, "projects", "problem_message", "TEXT")


# Append only. Editing an entry that has already shipped changes nothing on a
# database that ran it -- add the next one instead.
MIGRATIONS = [
    _v1_projects_and_forwards,
    _v2_project_problem,
]
SCHEMA_VERSION = len(MIGRATIONS)


def _read_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version "
                 "(version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return int(row[0]) if row else 0


def _write_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
    conn.commit()


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
    for index in range(version, SCHEMA_VERSION):
        MIGRATIONS[index](conn)
        # Recorded per step, not once at the end: an agent killed mid-list
        # comes back knowing exactly which steps already ran.
        _write_version(conn, index + 1)
    return SCHEMA_VERSION
