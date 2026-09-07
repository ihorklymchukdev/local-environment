from agent.core.state import State


def test_add_and_get_project(tmp_path):
    s = State(tmp_path / "s.db")
    s.add_project("myproj", "/opt/omelet/projects/myproj", "myproj.d.io")
    row = s.get_project("myproj")
    assert row["guest_path"] == "/opt/omelet/projects/myproj"
    assert row["status"] == "stopped"


def test_projects_survive_reopen(tmp_path):
    db = tmp_path / "s.db"
    s = State(db)
    s.add_project("p1", "/g/p1", "p1.d.io", status="running")
    s.close()
    reopened = State(db)
    assert reopened.get_project("p1")["status"] == "running"


def test_remove_project_forgets_it(tmp_path):
    s = State(tmp_path / "s.db")
    s.add_project("p", "/g/p", "p.d.io")
    s.remove_project("p")
    assert s.get_project("p") is None


def test_state_serves_threads_other_than_the_one_that_opened_it(tmp_path):
    # sqlite3 refuses a connection used off its creating thread, and every
    # route runs in FastAPI's threadpool while jobs run on threads of their
    # own. Two writers on one row must also leave a value that was actually
    # written, not a half-applied one.
    import threading

    s = State(tmp_path / "s.db")
    s.add_project("p", "/g/p", "p.d.io")
    start = threading.Barrier(6)
    errors: list[BaseException] = []

    def hammer(n: int):
        try:
            start.wait(5)
            for _ in range(20):
                s.set_status("p", f"status-{n}")
                s.set_problem("p", f"code-{n}", f"message-{n}")
                assert s.get_project("p") is not None
                s.list_projects()
        except BaseException as e:  # noqa: BLE001 - reported, not swallowed
            errors.append(e)

    threads = [threading.Thread(target=hammer, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert not errors, f"state failed off-thread: {errors}"
    assert s.get_project("p")["status"] in {f"status-{n}" for n in range(6)}
