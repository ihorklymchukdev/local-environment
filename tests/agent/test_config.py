from pathlib import Path

from agent.core.config import AgentConfig


def test_from_env_reads_the_names_the_container_will_set():
    # These names are the contract with the agent's compose file.
    config = AgentConfig.from_env({
        "OMELET_DOMAIN": "box.local",
        "OMELET_EDGE_PORT": "8080",
        "OMELET_PROJECTS_ROOT": "/srv/projects",
        "OMELET_STATE_DB": "/srv/state.db",
        "OMELET_AGENT_VERSION": "1.2.3",
        "OMELET_AGENT_HOST": "127.0.0.1",
        "OMELET_AGENT_PORT": "9000",
    })
    assert config.domain == "box.local"
    assert config.edge_port == 8080, "the port must arrive as an int, not a string"
    assert config.projects_root == Path("/srv/projects")
    assert config.state_db == Path("/srv/state.db")
    assert config.version == "1.2.3"
    assert (config.bind_host, config.port) == ("127.0.0.1", 9000)
