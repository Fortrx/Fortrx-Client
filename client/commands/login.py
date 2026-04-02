import typer
from rich.console import Console
from client.network.auth import login as login_user,get_me
from client.network import FortrxAPIError
from client.storage import save_token

app = typer.Typer()
console = Console()

@app.command()
def login(
    username:str = typer.Argument(...,help="Your Username"),
    password:str = typer.Option(...,prompt=True,hide_input = True)
    ):
    try:
        token = login_user(username,password)
        me = get_me()
        console.print(f"[green]✅ Logged in![/green] Hello, {me['username']}")
        console.print(f" User ID: [bold]{me['id']}[/bold]")
        
        save_token(token)
        console.print(f"[dim]  Session saved locally[/dim]")
    except FortrxAPIError as e:
        console.print(f"[red]❌ Login failed:[/red] {e.detail}")
        raise typer.Exit(1)