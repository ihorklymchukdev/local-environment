import ast
from pathlib import Path

# Anchored to this file, never to the working directory: a cwd-relative
# Path("host") scans nothing and passes vacuously when pytest runs elsewhere.
HOST = Path(__file__).resolve().parents[2] / "host"

# The Protocol describes one idea: make a Linux VM exist, and let me reach it.
# A method that carries project data across the boundary belongs to the agent,
# and adding one here must break this test rather than pass unnoticed.
LIFECYCLE_SURFACE = {
    "is_supported",
    "preflight",
    "apply_remedy",
    "reboot_required",
    "exists",
    "create",
    "start",
    "stop",
    "destroy",
    "exec",
    "forward",
}


def _protocol_methods() -> set[str]:
    source = (HOST / "core" / "provider.py").read_text()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef) and node.name == "VmProvider":
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"no VmProvider class in {HOST / 'core' / 'provider.py'}")


def test_protocol_is_exactly_the_lifecycle_surface():
    assert _protocol_methods() == LIFECYCLE_SURFACE


def test_every_provider_implements_the_whole_surface():
    # Providers are duck-typed against the Protocol rather than subclassing it,
    # so nothing but this test notices a method that was renamed on one side.
    from host.providers.lima import LimaProvider
    from host.providers.wsl2 import Wsl2Provider

    for cls in (LimaProvider, Wsl2Provider):
        missing = [name for name in LIFECYCLE_SURFACE if not callable(getattr(cls, name, None))]
        assert not missing, f"{cls.__name__} does not implement {missing}"
