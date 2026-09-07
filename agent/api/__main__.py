from __future__ import annotations

import uvicorn

from ..core import constants
from ..core.config import AgentConfig
from .app import create_app


def main() -> None:
    config = AgentConfig.from_env()
    # 0.0.0.0 because the host reaches the agent through the VM's port
    # mapping; narrowing the bind address is a later task's decision.
    uvicorn.run(create_app(config=config), host="0.0.0.0",
                port=constants.AGENT_PORT)


if __name__ == "__main__":
    main()
