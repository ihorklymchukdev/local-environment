import ast
from pathlib import Path

# Anchored to this file, never to the working directory: a cwd-relative
# Path("host") scans nothing and passes vacuously when pytest runs elsewhere.
HOST = Path(__file__).resolve().parents[2] / "host"

# `exec()` survives the thinning for three jobs: getting the VM provisioned,
# reading the token that lets the host talk to the agent over HTTP, and the
# readiness probe's own cheap reachability check (`exec(["true"])`) and engine
# marker read (`exec(["cat", ...])`) -- both facts the probe must establish
# itself, before there is a client to ask anything of. Every other use is
# project logic reaching across the boundary by shelling into the guest, which
# is what Phase 1 moved into the agent. A new entry here is a design decision,
# not a formality.
ALLOWED_CALLERS = {
    ("core/bootstrap.py", "_run"),
    ("core/bootstrap.py", "_installed"),
    ("client.py", "read_token"),
    ("core/status.py", "probe"),
}


def _exec_callers(tree, rel: str):
    """Yield (rel, enclosing function, lineno) for every `<x>.exec(...)` call.

    Walks each function body separately rather than the module tree, so the
    enclosing name is the real one -- ast.walk alone loses it.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if (isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "exec"):
                yield rel, node.name, child.lineno


def test_exec_is_only_used_for_bootstrap_and_the_token():
    offenders = []
    found = []
    scanned = [py for py in sorted(HOST.rglob("*.py")) if "providers" not in py.parts]
    assert scanned, f"scanned nothing under {HOST}"
    for py in scanned:
        rel = py.relative_to(HOST).as_posix()
        for rel, func, lineno in _exec_callers(ast.parse(py.read_text()), rel):
            found.append((rel, func))
            if (rel, func) not in ALLOWED_CALLERS:
                offenders.append(f"{rel}:{lineno} in {func}()")
    assert not offenders, (
        "provider.exec() was called outside bootstrap and the token read: "
        f"{offenders}. Shelling into the guest to do project work is what the "
        "agent's HTTP API replaced -- add a route there instead.")
    # Guards against the allowlist outliving the code it describes.
    assert set(found) == ALLOWED_CALLERS, (
        f"ALLOWED_CALLERS no longer matches the tree: found {sorted(set(found))}")
