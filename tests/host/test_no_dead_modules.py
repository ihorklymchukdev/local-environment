import ast
from pathlib import Path

# Anchored to this file, never to the working directory: a cwd-relative
# Path("host") scans nothing and passes vacuously when pytest runs elsewhere.
HOST = Path(__file__).resolve().parents[2] / "host"

# The console entry point in pyproject.toml. Everything the host ships must be
# reachable from it; `host.setup_app.app` is reached through cli.setup()'s
# function-local import, which is still an import in the AST.
ROOTS = {"host.cli"}

# Files here are pushed into the VM and run there; the host never imports them.
PROVISION = HOST / "provision"


def _module_name(py: Path) -> str:
    rel = py.relative_to(HOST.parent).with_suffix("")
    parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
    return ".".join(parts)


def _host_imports(py: Path, module: str) -> set[str]:
    """Every `host.*` module this file imports, resolved to module names."""
    # A package's __init__ resolves `from .x` against the package itself; a
    # plain module resolves it against its parent. Getting this backwards makes
    # every provider look unreachable.
    package = module if py.name == "__init__.py" else module.rsplit(".", 1)[0]
    out = set()
    for node in ast.walk(ast.parse(py.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "host":
                    out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # `from ..core.provider import X` inside host.providers.wsl2:
                # the first dot is the package, each further dot climbs one.
                parts = package.split(".")
                base = parts[:len(parts) - (node.level - 1)]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if target.split(".")[0] != "host":
                continue
            out.add(target)
            # `from host.core import constants` names a module, not an attribute.
            out.update(f"{target}.{a.name}" for a in node.names)
    return out


def test_every_host_module_is_reachable_from_the_entry_point():
    """A module nothing imports is the most expensive kind of dead code: it
    still compiles, so the next reader cannot tell which copy is authoritative.
    Phase 2 moved project logic into the agent; anything left behind here that
    nobody calls should have gone with it."""
    files = sorted(py for py in HOST.rglob("*.py") if PROVISION not in py.parents)
    assert files, f"scanned nothing under {HOST}"
    modules = {_module_name(py): py for py in files}

    graph = {name: _host_imports(py, name) & set(modules) for name, py in modules.items()}
    # A package's __init__ is executed by any import of a module inside it.
    for name in modules:
        parent = name.rsplit(".", 1)[0]
        while parent and parent in modules:
            graph.setdefault(parent, set())
            graph[name] = graph[name] | {parent}
            parent = parent.rsplit(".", 1)[0] if "." in parent else ""

    reachable, queue = set(), list(ROOTS)
    while queue:
        name = queue.pop()
        if name in reachable or name not in graph:
            continue
        reachable.add(name)
        queue.extend(graph[name])

    orphans = sorted(set(modules) - reachable)
    assert not orphans, (
        f"nothing under host/ imports these modules: {orphans}. If their "
        "responsibility moved to the agent, delete them and their tests.")
