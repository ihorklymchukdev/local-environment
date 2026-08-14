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


from pathlib import Path as _Path


@app.command()
def up(directory: str = typer.Argument(".", help="Project directory with a docker-compose.yml")):
    """Bring a compose project up and print its URL(s)."""
    import yaml
    from runtime.core import constants
    from runtime.core.project import load_project, STARTED_OK, CRASH_LOOPING
    from runtime.core.lifecycle import push_project, compose_up
    from runtime.core.state import State
    from runtime.providers import default_install_dir

    local = _Path(directory).resolve()
    compose_dict = yaml.safe_load((local / "docker-compose.yml").read_text()) or {}
    pyml_path = local / ".runtime" / "project.yml"
    pyml = yaml.safe_load(pyml_path.read_text()) if pyml_path.exists() else None
    project = load_project(compose_dict, pyml, local.name)

    p = _provider()
    push_project(p, project.id, local)
    status, urls = compose_up(p, project, local, constants.DEFAULT_DOMAIN)

    state = State(default_install_dir().parent / "state.db")
    state.add_project(project.id, f"{constants.GUEST_PROJECTS}/{project.id}",
                      constants.DEFAULT_DOMAIN,
                      status="running" if status == STARTED_OK else "error")

    if status == STARTED_OK:
        for u in urls:
            typer.echo(f"  {u}")
    else:
        typer.echo(f"Project status: {status}. Run `runtime logs {project.id}`.")
        raise typer.Exit(code=1)


@app.command()
def down(project_id: str):
    """Stop a project's containers."""
    from runtime.core.lifecycle import compose_down
    compose_down(_provider(), project_id)
    typer.echo(f"{project_id} stopped.")


@app.command()
def status():
    """List known projects and their status."""
    from runtime.core.state import State
    from runtime.core import constants
    from runtime.providers import default_install_dir
    state = State(default_install_dir().parent / "state.db")
    rows = state.list_projects()
    if not rows:
        typer.echo("No projects.")
        return
    for r in rows:
        typer.echo(f"{r['id']:<20} {r['status']:<10} "
                   f"http://{r['id']}.{r['domain']}:{constants.EDGE_PORT}")


@app.command()
def logs(project_id: str, service: str = typer.Option(None)):
    """Show a project's container logs."""
    from runtime.core.lifecycle import project_logs
    typer.echo(project_logs(_provider(), project_id, service))


@app.command()
def destroy(project_id: str):
    """Stop and forget a project."""
    from runtime.core.lifecycle import compose_down
    from runtime.core.state import State
    from runtime.providers import default_install_dir
    compose_down(_provider(), project_id)
    State(default_install_dir().parent / "state.db").remove_project(project_id)
    typer.echo(f"{project_id} destroyed.")


if __name__ == "__main__":
    app()
