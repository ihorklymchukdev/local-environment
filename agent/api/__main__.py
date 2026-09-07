from __future__ import annotations

import uvicorn

from ..core.config import AgentConfig
from .app import create_app


def main() -> None:
    config = AgentConfig.from_env()
    # Defaults to 0.0.0.0 because the host reaches the agent through the VM's
    # port mapping; narrowing the bind address is a later task's decision.
    uvicorn.run(create_app(config=config), host=config.bind_host, port=config.port)


if __name__ == "__main__":
    main()
