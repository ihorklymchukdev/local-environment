from __future__ import annotations

import json
import re
from dataclasses import dataclass

import yaml

from .detect import detect_web, WebSpec
from .overlay import build_overlay

STARTED_OK = "started_ok"
FAILED_TO_START = "failed_to_start"
CRASH_LOOPING = "crash_looping"


@dataclass(frozen=True)
class Project:
    id: str
    webs: list[WebSpec]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")


def load_project(compose_dict: dict, project_yml: dict | None, dir_name: str) -> Project:
    project_yml = project_yml or {}
    pid = project_yml.get("id") or _slug(dir_name)
    if project_yml.get("web"):
        webs = [WebSpec(service=w["service"], port=int(w["port"]),
                        subdomain=w.get("subdomain"))
                for w in project_yml["web"]]
    else:
        webs = detect_web(compose_dict)
    return Project(id=pid, webs=webs)


def overlay_yaml(project: Project, domain: str) -> str:
    overlay = build_overlay(project.id, project.webs, domain)
    return yaml.safe_dump(overlay, sort_keys=False)


def classify(up_result, ps_json: str) -> str:
    if not up_result.ok:
        return FAILED_TO_START
    try:
        rows = json.loads(ps_json) if ps_json.strip() else []
    except json.JSONDecodeError:
        rows = []
    for row in rows:
        state = str(row.get("State", "")).lower()
        if state == "restarting" or (state == "exited" and row.get("ExitCode", 0) != 0):
            return CRASH_LOOPING
    return STARTED_OK
