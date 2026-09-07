import typer

from host.core.diagnose import render_diagnosis
from host.providers import get_provider

app = typer.Typer(help="Omelet: VM + Docker + one exposed port.", no_args_is_help=True)

_provider_factory = get_provider  # tests override this


def _provider():
    return _provider_factory()


@app.callback()
def callback():
    """Omelet CLI."""


@app.command()
def version():
    """Print the Omelet version."""
    typer.echo("omelet 0.1.0")


@app.command()
def doctor():
    """Report whether this host can run the VM, and how to fix what's missing."""
    provider = get_provider()
    diag = provider.is_supported()
    typer.echo(render_diagnosis(diag))
    raise typer.Exit(code=0 if diag.ok else 1)


vm = typer.Typer(help="Manage the Omelet VM.", no_args_is_help=True)
app.add_typer(vm, name="vm")


@vm.command("create")
def vm_create():
    """Create the VM and bootstrap Docker + Traefik inside it."""
    from host.core.bootstrap import bootstrap, BootstrapError
    p = _provider()
    if p.exists():
        typer.echo("VM already exists; bootstrapping (idempotent).")
    else:
        typer.echo("Creating VM…")
        p.create()
    typer.echo("Installing Docker + Traefik in the VM (a few minutes)…")
    try:
        bootstrap(p)
    except BootstrapError as e:
        typer.echo(f"\nBootstrap failed.\n{e}")
        raise typer.Exit(code=1)
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
    from agent.core import constants
    from agent.core.project import load_project, STARTED_OK
    from agent.core.lifecycle import push_project, compose_up
    from agent.core.state import State
    from host.providers import default_install_dir

    local = _Path(directory).resolve()
    compose_dict = yaml.safe_load((local / "docker-compose.yml").read_text()) or {}
    pyml_path = local / ".omelet" / "project.yml"
    pyml = yaml.safe_load(pyml_path.read_text()) if pyml_path.exists() else None
    project = load_project(compose_dict, pyml, local.name)

    p = _provider()
    push_project(p, project.id, local)
    status, urls, detail = compose_up(p, project, local, constants.DEFAULT_DOMAIN)

    state = State(default_install_dir().parent / "state.db")
    state.add_project(project.id, f"{constants.GUEST_PROJECTS}/{project.id}",
                      constants.DEFAULT_DOMAIN,
                      status="running" if status == STARTED_OK else "error")

    if status == STARTED_OK:
        for u in urls:
            typer.echo(f"  {u}")
    else:
        typer.echo(f"Project status: {status}. Run `omelet logs {project.id}`.")
        if detail:
            typer.echo(detail)
        raise typer.Exit(code=1)


@app.command()
def down(project_id: str):
    """Stop a project's containers."""
    from agent.core.lifecycle import compose_down
    compose_down(_provider(), project_id)
    typer.echo(f"{project_id} stopped.")


@app.command()
def status():
    """List known projects and their status."""
    from agent.core.state import State
    from agent.core import constants
    from host.providers import default_install_dir
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
    from agent.core.lifecycle import project_logs
    result = project_logs(_provider(), project_id, service)
    if not result.ok:
        typer.echo(result.stderr.strip() or "could not read the logs", err=True)
        raise typer.Exit(1)
    typer.echo(result.stdout)


@app.command()
def destroy(project_id: str):
    """Stop and forget a project."""
    from agent.core.lifecycle import compose_down
    from agent.core.state import State
    from host.providers import default_install_dir
    compose_down(_provider(), project_id)
    State(default_install_dir().parent / "state.db").remove_project(project_id)
    typer.echo(f"{project_id} destroyed.")


@app.command()
def setup(resume: bool = typer.Option(False, "--resume"),
          headless: bool = typer.Option(False, "--headless")):
    """Set up everything: check the host, create the VM, install Docker."""
    import sys as _sys
    from agent.core import constants
    from host.core.install import (
        RESUME_NOTICE, VERIFY_TEMPLATE, DeadEnd, InstallError, InstallState, Progress,
        RebootRequired, default_steps, run_install,
    )
    from host.providers import default_install_dir

    root = default_install_dir().parent
    provider = _provider()
    state = InstallState(root / "install-state.json")
    steps = default_steps(
        provider,
        cache_dir=root / "cache",
        template_dir=VERIFY_TEMPLATE,
        domain=constants.DEFAULT_DOMAIN,
        exe_path=_sys.executable,
        install_dir=default_install_dir(),
    )

    def report(progress: Progress):
        if progress.status not in ("running", "done", "failed"):
            return
        typer.echo(f"[{progress.status:>7}] {progress.step}")
        if progress.message:
            typer.echo(progress.message)

    if not headless:
        from host.setup_app.app import run_window
        raise typer.Exit(code=run_window(steps, state, resumed=resume))

    if resume:
        typer.echo(RESUME_NOTICE)
    try:
        run_install(steps, state, report)
    except RebootRequired:
        typer.echo("\nRestart your computer. Setup will continue on its own "
                   "when you log back in.")
        raise typer.Exit(code=2)
    except DeadEnd as e:
        typer.echo(f"\nThis computer needs a change before setup can continue:\n\n{e}")
        raise typer.Exit(code=1)
    except InstallError as e:
        typer.echo(f"\nSetup failed during {e.step}:\n\n{e.message}")
        if e.action:
            typer.echo(f"\nWhat to do: {e.action}")
        raise typer.Exit(code=1)


@app.command()
def uninstall(purge: bool = typer.Option(False, "--purge")):
    """Remove the VM and all cached data. Destroys every project inside it."""
    if not purge:
        typer.echo("This destroys the VM and every project inside it. "
                   "Re-run with --purge to confirm.")
        raise typer.Exit(code=1)
    import shutil
    from host.core.install import InstallState
    from host.providers import default_install_dir

    destroy_error = None
    try:
        _provider().destroy()
    except Exception as e:
        destroy_error = e

    install_dir = default_install_dir()
    root = install_dir.parent
    InstallState(root / "install-state.json").clear()
    shutil.rmtree(root / "cache", ignore_errors=True)
    # The VM's own directory: wsl --unregister normally empties it, but a
    # failed or partial destroy leaves a multi-gigabyte vhdx behind.
    shutil.rmtree(install_dir, ignore_errors=True)
    try:
        (root / "state.db").unlink(missing_ok=True)
    except OSError as e:
        typer.echo(f"Could not remove {root / 'state.db'} ({e}).")

    if destroy_error is not None:
        typer.echo(f"The VM could not be removed ({destroy_error}). "
                   "Local data was cleaned up anyway.")
        raise typer.Exit(code=1)
    typer.echo("Removed.")


@app.command()
def selfcheck():
    """Verify bundled assets resolve on disk, the way the real code reads them.

    A frozen build can pass `version` while still missing a bundled asset —
    `version` never touches disk. This walks the same resolution each asset's
    real caller uses, so a packaging mistake (a bad PyInstaller `datas` entry)
    is caught by running the exe, not discovered by a user mid-setup.
    """
    from pathlib import Path
    from host.core.bootstrap import guest_assets
    from host.core.install import VERIFY_TEMPLATE
    import host.providers as _providers

    # Derived from the push list rather than restated, so an asset can never be
    # added or dropped without this check following it -- that gap is how a
    # deleted traefik.yml stayed in the bundle with nothing failing.
    checks = [("/".join(local.parts[-3:]), local) for local, _remote in guest_assets()]
    checks += [
        ("agent/templates/nginx-hello/docker-compose.yml",
         VERIFY_TEMPLATE / "docker-compose.yml"),
        ("host/providers/omelet.yaml", Path(_providers.__file__).parent / "omelet.yaml"),
    ]

    all_ok = True
    for label, path in checks:
        ok = path.is_file()
        all_ok = all_ok and ok
        typer.echo(f"{'OK' if ok else 'MISSING':<7} {label} -> {path}")

    raise typer.Exit(code=0 if all_ok else 1)


if __name__ == "__main__":
    app()
