import os

import typer
from rich.console import Console

from client.services.daemon import daemon_status, run_daemon, start_daemon, stop_daemon


app = typer.Typer()
console = Console()


@app.command("start")
def daemon_start(
    password: str = typer.Option(None, "--password", "-p", help="Storage password"),
):
    password = password or os.getenv("FORTRX_DAEMON_PASSWORD")
    if not password:
        password = typer.prompt("Storage password", hide_input=True)
    state = start_daemon(password)
    console.print(f"[green]Daemon[/green] {state.get('status', 'started')}")
    if state.get("pid"):
        console.print(f" PID: [bold]{state['pid']}[/bold]")


@app.command("run")
def daemon_run(
    password: str = typer.Option(None, "--password", "-p", help="Storage password"),
):
    password = password or os.getenv("FORTRX_DAEMON_PASSWORD")
    if not password:
        password = typer.prompt("Storage password", hide_input=True)
    run_daemon(password)


@app.command("status")
def daemon_status_cmd():
    state = daemon_status()
    status = "running" if state.get("is_running") else state.get("status", "stopped")
    console.print(f"[cyan]Daemon status:[/cyan] {status}")
    if state.get("pid"):
        console.print(f" PID: [bold]{state['pid']}[/bold]")
    if state.get("updated_at"):
        console.print(f" Updated: [dim]{state['updated_at']}[/dim]")


@app.command("stop")
def daemon_stop():
    result = stop_daemon()
    if result.get("stopped"):
        console.print(f"[yellow]Stopped daemon[/yellow] PID {result['pid']}")
        return
    console.print(f"[dim]Daemon not stopped:[/dim] {result.get('reason', 'not running')}")
