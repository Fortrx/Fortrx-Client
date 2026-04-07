import typer
from rich.console import Console
from client.network.auth import login as login_user,get_me
from client.network import FortrxAPIError
from client.storage.token_store import save_token
from client.services.daemon import start_daemon

app = typer.Typer()
console = Console()

@app.command()
def login(
    username:str = typer.Argument(...,help="Your Username"),
    password:str = typer.Option(...,prompt=True,hide_input = True),
    storage_password: str = typer.Option(None, "--storage-password", "-s"),
    start_daemon_after: bool = typer.Option(True, "--start-daemon/--no-start-daemon"),
    ):
    try:
        if not storage_password:
            storage_password = typer.prompt("Storage password", hide_input=True)
        token = login_user(username,password)
        me = get_me()
        console.print(f"[green]✅ Logged in![/green] Hello, {me['username']}")
        console.print(f" User ID: [bold]{me['id']}[/bold]")
        
        save_token(token, password=storage_password)
        console.print(f"[dim]  Session saved locally[/dim]")
        if start_daemon_after:
            state = start_daemon(storage_password)
            console.print(f"[dim]  Daemon {state.get('status', 'starting')}[/dim]")
    except FortrxAPIError as e:
        console.print(f"[red]❌ Login failed:[/red] {e.detail}")
        raise typer.Exit(1)
