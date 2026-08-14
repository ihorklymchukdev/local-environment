from runtime.core.project import (
    load_project, classify, overlay_yaml,
    STARTED_OK, FAILED_TO_START, CRASH_LOOPING,
)
from runtime.core.provider import Completed
import yaml


def test_load_project_uses_explicit_web_over_detection():
    compose = {"services": {"a": {"image": "x", "ports": ["1:2"]},
                            "b": {"image": "y", "ports": ["3:4"]}}}
    proj = load_project(compose, {"id": "custom", "web": [{"service": "b", "port": 4}]}, "dir")
    assert proj.id == "custom"
    assert [w.service for w in proj.webs] == ["b"]


def test_load_project_falls_back_to_detection_and_dirname():
    compose = {"services": {"only": {"image": "nginx", "ports": ["8080:80"]}}}
    proj = load_project(compose, None, "My Dir")
    assert proj.id == "my-dir"          # sanitized directory name
    assert proj.webs[0].service == "only"


def test_classify_failed_to_start_on_nonzero_up():
    assert classify(Completed(1, "", "boom"), "[]") == FAILED_TO_START


def test_classify_crash_looping_on_restarting_container():
    ps = '[{"Service":"web","State":"restarting","ExitCode":1}]'
    assert classify(Completed(0, "", ""), ps) == CRASH_LOOPING


def test_classify_started_ok_when_running():
    ps = '[{"Service":"web","State":"running","ExitCode":0}]'
    assert classify(Completed(0, "", ""), ps) == STARTED_OK


def test_overlay_yaml_roundtrips_to_expected_structure():
    compose = {"services": {"web": {"image": "nginx", "ports": ["8080:80"]}}}
    proj = load_project(compose, None, "p")
    parsed = yaml.safe_load(overlay_yaml(proj, "d.io"))
    assert parsed["services"]["web"]["labels"]["traefik.enable"] == "true"
