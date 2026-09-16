"""Every folder under engine/skills is installed by `npx skills add` and
registered by its frontmatter name; the skills hand off to each other by
name. A mismatched name or a rename installs a skill nobody can call."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "engine" / "skills"
INSTRUCTIONS = ROOT / "engine" / "instructions" / "omelet.md"

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_SKILL_REF = re.compile(r"\bomelet-[a-z]+(?:-[a-z]+)*\b")
_LOCAL_FILE = re.compile(r"`((?:references|assets)/[^`]+)`")


def _skills() -> dict[str, Path]:
    found = {p.name: p / "SKILL.md" for p in SKILLS.iterdir() if p.is_dir()}
    assert len(found) >= 5, f"scanned {SKILLS}, found {sorted(found)}"
    return found


def _frontmatter(skill_md: Path) -> dict[str, str]:
    m = _FRONTMATTER.match(skill_md.read_text())
    assert m, f"{skill_md} has no frontmatter"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_frontmatter_name_matches_the_folder():
    for folder, skill_md in _skills().items():
        fm = _frontmatter(skill_md)
        assert fm.get("name") == folder, f"{skill_md}: name={fm.get('name')!r}"


def test_description_states_when_to_use_and_stays_short():
    for folder, skill_md in _skills().items():
        description = _frontmatter(skill_md).get("description", "")
        assert description.startswith("Use when"), f"{folder}: {description[:40]!r}"
        assert len(description) <= 500, f"{folder}: {len(description)} chars"


def test_every_skill_named_in_a_hand_off_exists():
    skills = _skills()
    for src in list(skills.values()) + [INSTRUCTIONS]:
        for name in set(_SKILL_REF.findall(src.read_text())):
            assert name in skills, f"{src.relative_to(ROOT)} refers to {name}"


def test_every_bundled_file_a_skill_points_at_exists():
    for folder, skill_md in _skills().items():
        for rel in set(_LOCAL_FILE.findall(skill_md.read_text())):
            assert (skill_md.parent / rel).is_file(), f"{folder}: {rel}"
