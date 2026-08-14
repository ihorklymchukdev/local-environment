import typer

app = typer.Typer(help="Local Runtime: VM + Docker + one exposed port.", no_args_is_help=True)


@app.callback()
def callback():
    """Local Runtime CLI."""


@app.command()
def version():
    """Print the runtime version."""
    typer.echo("runtime 0.1.0")


if __name__ == "__main__":
    app()
