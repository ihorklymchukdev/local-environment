from .provider import Diagnosis


def render_diagnosis(diag: Diagnosis) -> str:
    lines = []
    for c in diag.checks:
        mark = "✓" if c.ok else "✗"
        line = f"{mark} {c.label}"
        if c.fix:
            line += f"\n    → {c.fix}"
        lines.append(line)
    verdict = "All required checks passed." if diag.ok else \
        "Some checks failed — see the fixes above."
    lines.append("")
    lines.append(verdict)
    return "\n".join(lines)
