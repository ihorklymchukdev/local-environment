from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .migrate import migrate


class State:
    """The agent's project list, on one connection shared by every thread.

    FastAPI serves sync routes from a threadpool and jobs run on threads of
    their own, so a thread-bound connection fails as soon as a second thread
    touches it. One connection with `check_same_thread=False` behind a lock
    holds for both, and — unlike a connection per thread — nothing accumulates
    an open handle for every worker the threadpool ever created.
    """

    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            migrate(self._conn)

    def add_project(self, id, guest_path, domain, status="stopped"):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO projects(id, guest_path, domain, status) "
                "VALUES (?,?,?,?)", (id, guest_path, domain, status))
            self._conn.commit()

    def get_project(self, id):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM projects WHERE id=?", (id,)).fetchone()
        return dict(row) if row else None

    def list_projects(self):
        with self._lock:
            return [dict(r) for r in
                    self._conn.execute("SELECT * FROM projects ORDER BY id")]

    def set_status(self, id, status):
        with self._lock:
            self._conn.execute("UPDATE projects SET status=? WHERE id=?",
                               (status, id))
            self._conn.commit()

    def set_problem(self, id, code=None, message=None):
        """`code=None` clears it: a problem that outlives the fix is worse than
        none, so every `up` writes this whether or not it found something."""
        with self._lock:
            self._conn.execute(
                "UPDATE projects SET problem_code=?, problem_message=? WHERE id=?",
                (code, message, id))
            self._conn.commit()

    def remove_project(self, id):
        with self._lock:
            self._conn.execute("DELETE FROM projects WHERE id=?", (id,))
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()
