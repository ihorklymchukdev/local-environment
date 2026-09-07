import ast
from pathlib import Path


def _imported_modules(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            yield node.lineno, node.module or ""


AGENT = Path(__file__).resolve().parents[2] / "agent"


def test_agent_never_imports_from_host():
    # The agent ships as a Docker image built from agent/ alone; an import of
    # host code would only fail once the image runs.
    offenders = []
    scanned = sorted(AGENT.rglob("*.py"))
    assert scanned, f"scanned nothing under {AGENT}"
    for py in scanned:
        for lineno, module in _imported_modules(ast.parse(py.read_text())):
            if module == "host" or module.startswith("host."):
                offenders.append(f"{py}:{lineno} imports {module}")
    assert not offenders, f"agent/ imported host code: {offenders}"
