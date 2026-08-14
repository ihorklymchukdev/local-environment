import typer

from runtime.core.diagnose import render_diagnosis
from runtime.providers import get_provider

app = typer.Typer(help="Local Runtime: VM + Docker + one exposed port.", no_args_is_help=True)


@app.callback()
def callback():
    """Local Runtime CLI."""


@app.command()
def version():
    """Print the runtime version."""
    typer.echo("runtime 0.1.0")


@app.command()
def doctor():
    """Report whether this host can run the VM, and how to fix what's missing."""
    provider = get_provider()
    diag = provider.is_supported()
    typer.echo(render_diagnosis(diag))
    raise typer.Exit(code=0 if diag.ok else 1)


if __name__ == "__main__":
    app()
