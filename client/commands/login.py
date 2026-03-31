import typer
from rich.console import Console
from client.network.auth import login as login_user,get_me
from client.network import FortrxAPIError

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
        console.print(f" Token: {token[:30]}...")
    except FortrxAPIError as e:
        console.print(f"[red]❌ Login failed:[/red] {e.detail}")
        raise typer.Exit(1)