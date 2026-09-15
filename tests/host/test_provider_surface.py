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


# Not part of the Protocol, and deliberately so: the Protocol is the lifecycle,
# and these exist only so `default_steps` can build an install list without
# asking what platform it is on. They are still a contract every provider owes,
# and nothing noticed that LimaProvider owed two of them and had neither --
# `omelet setup` on macOS died with an AttributeError before its first step.
INSTALL_SURFACE = {"image", "register_resume", "location", "terminal",
                   "remediable", "runtime", "access"}


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


def test_every_provider_answers_what_the_install_list_asks_of_it():
    from host.providers.lima import LimaProvider
    from host.providers.wsl2 import Wsl2Provider

    for cls in (LimaProvider, Wsl2Provider):
        missing = [name for name in INSTALL_SURFACE if not hasattr(cls, name)]
        assert not missing, (
            f"{cls.__name__} does not provide {missing}. host/core/install.py "
            "reads these off whichever provider it was handed, so a provider "
            "missing one fails at setup time on that platform only.")


def test_the_install_surface_stays_out_of_the_lifecycle_protocol():
    # Kept apart on purpose: the Protocol answers "make a Linux VM exist and let
    # me reach it". Where the VM sits on disk and which terminal to name in a
    # success message are installer copy, not lifecycle.
    assert not (INSTALL_SURFACE & LIFECYCLE_SURFACE)
    assert not (INSTALL_SURFACE & _protocol_methods())
