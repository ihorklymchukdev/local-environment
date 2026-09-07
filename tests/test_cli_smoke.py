from typer.testing import CliRunner
from host.cli import app

runner = CliRunner()


def test_version_command_runs():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "omelet 0.1.0" in result.stdout
