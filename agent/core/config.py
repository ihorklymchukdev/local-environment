from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import constants
from .. import __version__


@dataclass(frozen=True)
class AgentConfig:
    """Everything the agent is allowed to vary at run time. Nothing else may
    hardcode the domain or the entry port.

    In production `projects_root` must stay `/opt/omelet/projects`: compose
    files are parsed here but the bind-mount paths inside them are resolved by
    dockerd on the VM, and `core/lifecycle.py` builds the guest paths it hands
    to compose from `constants.GUEST_PROJECTS`.
    """

    bind_host: str = "0.0.0.0"
    port: int = constants.AGENT_PORT
    domain: str = constants.DEFAULT_DOMAIN
    edge_port: int = constants.EDGE_PORT
    projects_root: Path = Path(constants.GUEST_PROJECTS)
    state_db: Path = Path(f"{constants.GUEST_ROOT}/state.db")
    # The shared secret bootstrap.sh generates in the guest. Phase 3 replaces
    # it with a service-issued device token; see agent/api/app.py's auth check.
    token_path: Path = Path(f"{constants.GUEST_ROOT}/agent.token")
    # A runaway/abuse guard on file uploads, not a policy -- generous enough
    # that no real project hits it. Raise via env, no rebuild needed.
    max_upload_bytes: int = 512 * 1024 * 1024
    version: str = __version__

    @classmethod
    def from_env(cls, env: dict | None = None) -> "AgentConfig":
        env = os.environ if env is None else env
        return cls(
            bind_host=env.get("OMELET_AGENT_HOST", "0.0.0.0"),
            port=int(env.get("OMELET_AGENT_PORT", constants.AGENT_PORT)),
            domain=env.get("OMELET_DOMAIN", constants.DEFAULT_DOMAIN),
            edge_port=int(env.get("OMELET_EDGE_PORT", constants.EDGE_PORT)),
            projects_root=Path(env.get("OMELET_PROJECTS_ROOT",
                                       constants.GUEST_PROJECTS)),
            state_db=Path(env.get("OMELET_STATE_DB",
                                  f"{constants.GUEST_ROOT}/state.db")),
            token_path=Path(env.get("OMELET_AGENT_TOKEN",
                                    f"{constants.GUEST_ROOT}/agent.token")),
            max_upload_bytes=int(env.get("OMELET_MAX_UPLOAD_BYTES",
                                         512 * 1024 * 1024)),
            version=env.get("OMELET_AGENT_VERSION", __version__),
        )
