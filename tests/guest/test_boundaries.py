import ast
import sys

from tests.guest.loader import GUEST_CLI, load


def test_the_guest_cli_imports_only_the_standard_library():
    # It is copied into a VM on its own: an import of host/, agent/ or a
    # third-party package works in this checkout and fails only in the guest.
    imported = set()
    for node in ast.walk(ast.parse(GUEST_CLI.read_text())):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import at line {node.lineno}"
            imported.add((node.module or "").split(".")[0])
    assert imported, f"scanned no imports in {GUEST_CLI}"
    outside = sorted(imported - set(sys.stdlib_module_names))
    assert not outside, f"the guest CLI imports non-stdlib modules: {outside}"


def test_start_stack_is_built_from_the_declared_stack_path():
    # A second literal here would let the two drift the way START_STACK's
    # hardcoded path used to risk against GUEST_ROOT/GUEST_STACK elsewhere.
    cli = load()
    assert cli.GUEST_STACK in cli.START_STACK


def test_the_guest_cli_slugs_project_names_the_way_the_agent_does():
    # The agent derives the project folder from the slugged id; a guest that
    # slugs differently checks one folder and registers another.
    from agent.core.project import _slug
    for name in ("Blog", "my app", "My.Repo", "--x--", "Ünïcode 2", "a__b", ""):
        assert load().project_id_for(name) == _slug(name), name
