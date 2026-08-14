import typer

from runtime.core.diagnose import render_diagnosis
from runtime.providers import get_provider

app = typer.Typer(help="Local Runtime: VM + Docker + one exposed port.", no_args_is_help=True)

_provider_factory = get_provider  # tests override this


def _provider():
    return _provider_factory()


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


vm = typer.Typer(help="Manage the runtime VM.", no_args_is_help=True)
app.add_typer(vm, name="vm")


@vm.command("create")
def vm_create():
    """Create the VM and bootstrap Docker + Traefik inside it."""
    from runtime.core.bootstrap import bootstrap
    p = _provider()
    if p.exists():
        typer.echo("VM already exists; bootstrapping (idempotent).")
    else:
        typer.echo("Creating VM…")
        p.create()
    bootstrap(p)
    typer.echo("VM ready.")


@vm.command("start")
def vm_start():
    _provider().start()
    typer.echo("VM started.")


@vm.command("stop")
def vm_stop():
    _provider().stop()
    typer.echo("VM stopped.")


@vm.command("destroy")
def vm_destroy():
    _provider().destroy()
    typer.echo("VM destroyed.")


if __name__ == "__main__":
    app()
