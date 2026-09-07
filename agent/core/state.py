from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    guest_path TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'stopped',
    problem_code TEXT,
    problem_message TEXT
);
CREATE TABLE IF NOT EXISTS forwards (
    project_id TEXT NOT NULL,
    service TEXT NOT NULL,
    guest_port INTEGER NOT NULL,
    host_port INTEGER NOT NULL UNIQUE
);
"""


class State:
    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add_project(self, id, guest_path, domain, status="stopped"):
        self._conn.execute(
            "INSERT OR REPLACE INTO projects(id, guest_path, domain, status) "
            "VALUES (?,?,?,?)", (id, guest_path, domain, status))
        self._conn.commit()

    def get_project(self, id):
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id=?", (id,)).fetchone()
        return dict(row) if row else None

    def list_projects(self):
        return [dict(r) for r in
                self._conn.execute("SELECT * FROM projects ORDER BY id")]

    def set_status(self, id, status):
        self._conn.execute("UPDATE projects SET status=? WHERE id=?", (status, id))
        self._conn.commit()

    def set_problem(self, id, code=None, message=None):
        """`code=None` clears it: a problem that outlives the fix is worse than
        none, so every `up` writes this whether or not it found something."""
        self._conn.execute(
            "UPDATE projects SET problem_code=?, problem_message=? WHERE id=?",
            (code, message, id))
        self._conn.commit()

    def remove_project(self, id):
        self._conn.execute("DELETE FROM forwards WHERE project_id=?", (id,))
        self._conn.execute("DELETE FROM projects WHERE id=?", (id,))
        self._conn.commit()

    def add_forward(self, project_id, service, guest_port, host_port):
        self._conn.execute(
            "INSERT INTO forwards(project_id, service, guest_port, host_port) "
            "VALUES (?,?,?,?)", (project_id, service, guest_port, host_port))
        self._conn.commit()

    def allocate_host_port(self, start=39100, end=39200) -> int:
        used = {r["host_port"] for r in
                self._conn.execute("SELECT host_port FROM forwards")}
        for port in range(start, end + 1):
            if port not in used:
                return port
        raise RuntimeError(f"no free host port in range {start}-{end}")

    def close(self):
        self._conn.close()
