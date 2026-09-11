import re
import subprocess
from pathlib import Path

from host.core import constants

# Anchored to this file, never to the working directory: a cwd-relative path
# scans nothing and fails (or passes) for the wrong reason when pytest runs
# elsewhere. Same rule as tests/test_no_platform_leak.py and the two
# import-boundary tests.
ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "host" / "provision" / "bootstrap.sh"


def test_bootstrap_is_valid_bash():
    # `bash -n` parses without executing; catches syntax errors.
    result = subprocess.run(["bash", "-n", str(BOOTSTRAP)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_bootstrap_pins_docker_official_repo_not_docker_io():
    text = BOOTSTRAP.read_text()
    assert "download.docker.com" in text
    assert "docker.io" not in text


def test_bootstrap_writes_the_marker_path_the_host_reads_back():
    # bootstrap.py polls constants.BOOTSTRAP_MARKER after the script returns.
    # Two independent literals here would let the script write a marker the
    # host never finds, reported as "succeeded but left no version marker".
    assert constants.BOOTSTRAP_MARKER in BOOTSTRAP.read_text()


def test_bootstrap_guards_on_the_package_not_the_docker_binary():
    # Docker Desktop's WSL integration puts its own docker CLI on PATH. Guarding
    # on `command -v docker` skipped the install and then failed at
    # `systemctl enable` with "Unit file docker.service does not exist".
    code = [l for l in BOOTSTRAP.read_text().splitlines()
            if not l.lstrip().startswith("#")]
    assert any("dpkg -s docker-ce" in l for l in code)
    assert not any("command -v docker" in l for l in code)


# A word is being *run* only at the start of a line or right after a pipe,
# `&&`/`||`, `;`, `(`, `!`, or then/else/do. Anchoring on the line start alone
# missed `... || docker network create`, which is the same bug one operator in.
_BARE_DOCKER = re.compile(r"(?:^|[|&;(!]|\b(?:then|else|do)\s)\s*docker\b")


def test_bootstrap_invokes_docker_by_absolute_path():
    # A bare `docker` would reach Docker Desktop's CLI when its WSL integration
    # is on, sending this VM's containers to Desktop's engine instead.
    for line in _commands():
        assert not _BARE_DOCKER.search(line), f"bare docker invocation: {line}"


def test_smoke_test_template_publishes_no_host_port():
    # The template reaches the browser through Traefik on the edge network, so a
    # published port buys nothing and collides: the first real Windows run died
    # with "failed to bind host port 0.0.0.0:8080/tcp: address already in use".
    import yaml
    compose = yaml.safe_load(
        (ROOT / "host" / "provision" / "nginx-hello"
         / "docker-compose.yml").read_text())
    for name, svc in compose["services"].items():
        assert not svc.get("ports"), f"{name} publishes a host port"


def _commands() -> list[str]:
    """Executable lines only -- a comment mentioning `docker run traefik` must
    not satisfy or trip the assertions below."""
    return [l.strip() for l in BOOTSTRAP.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


def _index_of(needle: str) -> int:
    for i, line in enumerate(_commands()):
        if needle in line:
            return i
    raise AssertionError(f"bootstrap.sh has no line containing {needle!r}")


def test_bootstrap_brings_the_stack_up_with_compose_not_an_inline_container():
    # Traefik and the agent are one compose stack now; an inline `docker run`
    # would start a Traefik outside it that compose can never upgrade or stop.
    commands = _commands()
    assert any(f"compose -f {constants.GUEST_STACK}" in l and " up -d" in l
               for l in commands)
    assert not any("docker run" in l for l in commands), "the inline traefik container is gone"
    assert not any("docker rm -f traefik" in l for l in commands)
    assert not any("traefik.yml" in l for l in commands)


def test_bootstrap_always_pulls_before_bringing_the_stack_up():
    # Always pulling is the delivery decision: it is how an agent update reaches
    # an already-bootstrapped VM. `up -d` alone would keep running a stale image.
    assert _index_of(f"compose -f {constants.GUEST_STACK} pull") < _index_of(" up -d")


def test_bootstrap_makes_opt_omelet_writable_before_the_agent_starts():
    # The agent runs as a non-root user whose only shared credential with the VM
    # is the docker group. Root-owned 0755 here means it cannot create
    # /opt/omelet/state.db, and `restart: always` then loops it forever.
    up = _index_of(" up -d")
    assert _index_of("chgrp") < up
    assert any("docker" in l for l in _commands() if "chgrp" in l), \
        "the group the agent actually belongs to"
    # g+rwX is the line that grants the access; chgrp alone leaves 0755 and the
    # agent still cannot create state.db. X, not x, so files stay non-executable.
    assert _index_of("g+rwX") < up
    assert _index_of("g+s") < up, \
        "setgid, or project directories the agent creates lose the group"
    assert _index_of("mkdir -p " + constants.GUEST_PROJECTS) < _index_of("chgrp")


def test_bootstrap_writes_the_marker_last():
    # bootstrap.py treats a missing marker as failure, which only works while the
    # marker is the final step: written earlier, a failed pull looks bootstrapped.
    commands = _commands()
    marker = _index_of(f"> {constants.BOOTSTRAP_MARKER}")
    assert marker > _index_of(" up -d")
    assert marker >= len(commands) - 2, "nothing that can fail may run after the marker"


def test_bootstrap_generates_the_token_only_if_absent():
    # Bootstrap re-runs are normal (idempotency by design); regenerating the
    # token on every run would invalidate a credential the host is already
    # holding.
    assert "[[ ! -s " + constants.GUEST_TOKEN + " ]]" in BOOTSTRAP.read_text()


def test_bootstrap_generates_the_token_without_a_sigpipe_trap():
    # tr fed straight from /dev/urandom never terminates on its own; bounding
    # its output with a downstream `head -c` kills it with SIGPIPE the moment
    # head stops reading, and `set -o pipefail` then fails the whole script
    # for a byte count that was never wrong. Bounding /dev/urandom itself at
    # the head of the pipeline avoids the trap entirely.
    text = BOOTSTRAP.read_text()
    assert "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n'" in text
    assert "tr -dc" not in text


def test_bootstrap_writes_the_token_before_the_stack_comes_up():
    commands = _commands()
    token_write = _index_of(constants.GUEST_TOKEN)
    assert token_write < _index_of(" up -d")


def test_bootstrap_writes_the_token_after_the_permissions_sweep_widens_it():
    # A mode-600 token written before `chmod -R g+rwX /opt/omelet` comes out
    # group-readable; written after, its own chmod is the last word.
    commands = _commands()
    token_write = _index_of(f"[[ ! -s {constants.GUEST_TOKEN} ]]")
    assert _index_of("g+rwX") < token_write


def test_bootstrap_reasserts_a_narrow_mode_on_the_token_after_writing_it():
    commands = _commands()
    chmod = _index_of(f"chmod 640 {constants.GUEST_TOKEN}")
    assert chmod > _index_of(f"[[ ! -s {constants.GUEST_TOKEN} ]]")
    assert chmod < _index_of(" up -d")


def test_bootstrap_creates_the_token_at_a_narrow_mode_from_the_start():
    # A plain `>` redirect creates the file under root's umask (644) before
    # any later chmod narrows it, leaving a window where it is
    # world-readable. `install -m` sets the mode at creation instead.
    commands = _commands()
    create = _index_of(f"install -m 640 /dev/null {constants.GUEST_TOKEN}")
    assert create > _index_of(f"[[ ! -s {constants.GUEST_TOKEN} ]]")
    assert create < _index_of(f"head -c 32 /dev/urandom")


def test_bootstrap_chgrps_the_token_to_docker():
    # The other half of the 640/docker permission model: without this, the
    # token's group stays whatever `install`/root's process defaults to,
    # which the agent's own group membership may not be.
    commands = _commands()
    chgrp = _index_of(f"chgrp docker {constants.GUEST_TOKEN}")
    assert chgrp < _index_of(" up -d")
    assert chgrp < _index_of(f"chmod 640 {constants.GUEST_TOKEN}")


def test_bootstrap_writes_this_vms_real_docker_gid_for_the_stack():
    # stack.yml's group_add defaults to 999 and the image bakes in 999, but the
    # chgrp above uses whatever GID this VM's docker group actually has. On a VM
    # where they differ the agent can write neither /opt/omelet nor the socket
    # -- the same crash-loop the chgrp exists to prevent, one step over.
    commands = _commands()
    env_line = _index_of(f"{constants.GUEST_ROOT}/.env")
    assert env_line < _index_of(" up -d"), "compose reads .env when it starts"
    assert any("OMELET_DOCKER_GID" in l for l in commands)
    assert any("getent group docker" in l for l in commands), \
        "the GID must be read from the VM, not assumed"
    assert not any(re.search(r"OMELET_DOCKER_GID=[0-9]", l) for l in commands), \
        "a literal GID is the bug this guards against"


def test_bootstrap_installs_the_agent_files_where_the_host_pushes_them():
    # The host pushes to guest_assets()'s paths and the script reads them by
    # literal path; two independent spellings install nothing, silently.
    import posixpath
    from host.core.bootstrap import guest_assets

    remotes = {local.name: remote for local, remote in guest_assets()}
    text = "\n".join(_commands())
    assert remotes["omelet.py"] in text
    assert remotes["install-agents.sh"] in text
    assert posixpath.dirname(remotes["omelet.md"]) in text
