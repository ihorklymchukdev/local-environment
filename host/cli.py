from contextlib import contextmanager

import typer

from host.core.diagnose import render_diagnosis
from host.providers import get_provider

app = typer.Typer(help="Omelet: VM + Docker + one exposed port.", no_args_is_help=True)

_provider_factory = get_provider  # tests override this


def _provider():
    return _provider_factory()


def _default_client():
    from host.client import AgentClient
    return AgentClient.for_provider(_provider())


_client_factory = _default_client  # tests override this


def _client():
    return _client_factory()


@contextmanager
def _agent_errors():
    """Every failure the agent can report is already a sentence written for a
    user; printing a traceback or a status code over it loses the only text
    that says what went wrong."""
    from host.client import (AgentError, AgentUnavailableError, JobFailedError,
                             JobTimeoutError)
    try:
        yield
    except (AgentError, AgentUnavailableError, JobFailedError,
            JobTimeoutError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)


@contextmanager
def _vm_errors():
    """The providers raise a plain RuntimeError carrying `wsl.exe`'s own words
    when a VM operation fails. A traceback would bury the one line that says
    what happened."""
    try:
        yield
    except (RuntimeError, OSError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)


@app.callback()
def callback():
    """Omelet CLI."""


@app.command()
def version():
    """Print the Omelet version."""
    from host.core import constants

    typer.echo(f"omelet {constants.APP_VERSION}")


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
    """Create the VM and install Omelet inside it."""
    from host.core.bootstrap import bootstrap, BootstrapError
    with _vm_errors():
        p = _provider()
        if p.exists():
            typer.echo("VM already exists; checking the Omelet install.")
        else:
            typer.echo("Creating VM…")
            p.create()
        typer.echo("Installing Omelet in the VM (a few minutes)…")
        try:
            bootstrap(p)
        except BootstrapError as e:
            typer.echo(f"\nBootstrap failed.\n{e}")
            raise typer.Exit(code=1)
    typer.echo("VM ready.")


@vm.command("start")
def vm_start():
    with _vm_errors():
        _provider().start()
    typer.echo("VM started.")


@vm.command("stop")
def vm_stop():
    with _vm_errors():
        _provider().stop()
    typer.echo("VM stopped.")


@vm.command("destroy")
def vm_destroy():
    with _vm_errors():
        _provider().destroy()
    typer.echo("VM destroyed.")


port = typer.Typer(help="Reach a port inside the VM from this machine.",
                   no_args_is_help=True)
app.add_typer(port, name="port")


@port.command("add")
def port_add(guest_port: int, host_port: int):
    """Reach the VM's GUEST_PORT on this machine's HOST_PORT.

    For the ports the VM does not publish itself -- a database, a queue, a
    debugger -- so a tool on this machine can connect to one.
    """
    with _vm_errors():
        _provider().forward(guest_port, host_port)
    typer.echo(f"localhost:{host_port} now reaches port {guest_port} in the VM.")


@port.command("remove")
def port_remove(guest_port: int, host_port: int):
    """Stop reaching the VM's GUEST_PORT on HOST_PORT."""
    with _vm_errors():
        _provider().unforward(guest_port, host_port)
    typer.echo(f"localhost:{host_port} no longer reaches the VM.")


@port.command("list")
def port_list():
    """Show every port forward currently in place."""
    with _vm_errors():
        pairs = _provider().forwards()
    if not pairs:
        typer.echo("No port forwards.")
        return
    for guest_port, host_port in pairs:
        typer.echo(f"localhost:{host_port} -> {guest_port} in the VM")


from pathlib import Path as _Path


@app.command()
def up(directory: str = typer.Argument(".", help="Project directory with a docker-compose.yml")):
    """Bring a compose project up and print its URL(s)."""
    from host.client import JobFailedError, project_id_for
    from host.core.constants import COMPOSE_FILE

    local = _Path(directory).resolve()
    if not (local / COMPOSE_FILE).is_file():
        # Checked here so an empty folder is not registered as a project the
        # agent then has to refuse.
        typer.echo(f"There is no {COMPOSE_FILE} in {local}.", err=True)
        raise typer.Exit(code=1)
    project_id = project_id_for(local.name)

    with _agent_errors():
        client = _client()
        client.ensure_project(project_id)
        client.upload_directory(project_id, local)
        typer.echo(f"Starting {project_id} in the VM…")
        try:
            job = client.wait_for_job(client.project_up(project_id))
        except JobFailedError as e:
            status = e.result.get("status", "failed")
            # First line for the user, second for whoever they send it to: a
            # bare `crash_looping` is not a sentence anyone can act on.
            typer.echo(f"{project_id} started, but its containers did not stay "
                       f"running. To see what they printed, run: "
                       f"omelet logs {project_id}", err=True)
            typer.echo(f"(status: {status})", err=True)
            if str(e):
                typer.echo(str(e), err=True)
            raise typer.Exit(code=1)
        result = job.get("result") or {}
        urls = result.get("urls") or []
        if not urls:
            # A successful run that printed nothing at all leaves the user
            # unsure whether anything happened.
            typer.echo(f"{project_id} started. No service is exposed over HTTP.")
        for url in urls:
            typer.echo(f"  {url}")
        problem = result.get("problem")
        if problem:
            # The containers did start, so this is not a failure -- but the
            # URL above will not answer until the user acts on this.
            typer.echo(problem["message"], err=True)


@app.command()
def down(project_id: str):
    """Stop a project's containers."""
    with _agent_errors():
        client = _client()
        # Waited on, not fired and forgotten: `down` reporting success while
        # the containers are still stopping is a lie the next command trips on.
        client.wait_for_job(client.project_down(project_id))
    typer.echo(f"{project_id} stopped.")


@app.command()
def status():
    """List known projects and their status."""
    with _agent_errors():
        projects = _client().list_projects()
    if not projects:
        typer.echo("No projects.")
        return
    for project in projects:
        urls = project.get("urls") or []
        typer.echo(f"{project['id']:<20} {project['status']:<16} "
                   f"{urls[0] if urls else ''}".rstrip())
        for url in urls[1:]:
            typer.echo(f"    {url}")
        problem = project.get("problem")
        if problem:
            typer.echo(f"    problem: {problem['message']}")


@app.command()
def logs(project_id: str, service: str = typer.Option(None)):
    """Show a project's container logs."""
    with _agent_errors():
        text = _client().logs(project_id, service)
    typer.echo(text)


@app.command()
def destroy(project_id: str):
    """Stop and forget a project."""
    with _agent_errors():
        result = _client().delete_project(project_id)
    typer.echo(f"{project_id} destroyed.")
    if not result.get("stopped", True):
        # The project row is gone either way, so a failed `compose down` here
        # leaves containers running that nothing will list again.
        typer.echo("Its containers may still be running in the VM: "
                   f"{result.get('detail', '').strip()}", err=True)
        raise typer.Exit(code=1)


@app.command()
def setup(resume: bool = typer.Option(False, "--resume"),
          headless: bool = typer.Option(False, "--headless")):
    """Set up everything: check the host, create the VM, install Docker."""
    import sys as _sys
    from host.core import constants
    from host.core.install import (
        RESUME_NOTICE, VERIFY_TEMPLATE, DeadEnd, InstallError, InstallState, Progress,
        RebootRequired, default_steps, run_install,
    )
    from host.providers import default_install_dir

    root = default_install_dir().parent
    provider = _provider()
    state = InstallState(root / "install-state.json")

    def build_steps():
        return default_steps(
            provider,
            cache_dir=root / "cache",
            template_dir=VERIFY_TEMPLATE,
            domain=constants.DEFAULT_DOMAIN,
            exe_path=_sys.executable,
        )

    def report(progress: Progress):
        if progress.fraction is not None:
            return          # the window draws a bar; a terminal would print 100 lines
        if progress.status not in ("running", "done", "failed"):
            return
        typer.echo(f"[{progress.status:>7}] {progress.step}")
        if progress.message:
            typer.echo(progress.message)

    if not headless:
        from host.setup_app.app import run_window
        raise typer.Exit(code=run_window(provider, build_steps, state, resumed=resume))

    steps = build_steps()

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
    # No host-side state.db to remove any more: project state lives in the VM
    # at /opt/omelet/state.db and goes with the VM.

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
    from host.core.install import VERIFY_TEMPLATE
    import host.providers as _providers

    # Resolved from the modules that read them, not from this file: cli.py is
    # the frozen entry script, whose __file__ sits at the bundle root.
    checks = [
        ("host/provision/nginx-hello/docker-compose.yml",
         VERIFY_TEMPLATE / "docker-compose.yml"),
        ("host/providers/omelet.yaml", Path(_providers.__file__).parent / "omelet.yaml"),
    ]

    all_ok = True
    for label, path in checks:
        ok = path.is_file()
        all_ok = all_ok and ok
        typer.echo(f"{'OK' if ok else 'MISSING':<7} {label} -> {path}")

    # The setup window is five modules PyInstaller can only find through the
    # spec's hiddenimports. A bundle missing one launches, shows a Dock icon
    # and dies on the first draw -- which is exactly what this command exists
    # to catch before a user does.
    import importlib
    for name in ("theme", "widgets", "wizard", "status", "app"):
        importlib.import_module(f"host.setup_app.{name}")
    typer.echo("✓ setup window modules import")

    raise typer.Exit(code=0 if all_ok else 1)


if __name__ == "__main__":
    app()
