import re
from pathlib import Path

FORBIDDEN = re.compile(r"sys\.platform|platform\.system\(\)|os\.name")


def test_platform_branching_only_in_providers():
    offenders = []
    for root in ("host", "agent"):
        for py in Path(root).rglob("*.py"):
            if "providers" in py.parts:
                continue
            if FORBIDDEN.search(py.read_text()):
                offenders.append(str(py))
    assert not offenders, f"platform branching leaked outside providers/: {offenders}"
