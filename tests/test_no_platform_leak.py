import re
from pathlib import Path

FORBIDDEN = re.compile(r"sys\.platform|platform\.system\(\)|os\.name")

# Anchored to this file, never to the working directory: a cwd-relative
# Path("host") scans nothing and passes vacuously when pytest runs elsewhere.
ROOT = Path(__file__).resolve().parents[1]


def test_platform_branching_only_in_providers():
    offenders = []
    scanned = []
    for package in ("host", "agent"):
        for py in sorted((ROOT / package).rglob("*.py")):
            if "providers" in py.parts:
                continue
            scanned.append(py)
            if FORBIDDEN.search(py.read_text()):
                offenders.append(str(py))
    assert scanned, f"scanned nothing under {ROOT}"
    assert not offenders, f"platform branching leaked outside providers/: {offenders}"
