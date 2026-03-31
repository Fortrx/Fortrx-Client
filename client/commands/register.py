import typer
from rich.console import Console 
from client.network import FortrxAPIError
from client.network.auth import register as register_user

app = typer.Typer()
console = Console()

@app.command()
def register(
    username: str = typer.Argument(...,help="Your username"),
    email:str = typer.Argument(...,help="Your email"),
    password: str = typer.Option(...,prompt=True,hide_input=True)
    ):
    try:
        user = register_user(username,email,password)
        console.print(f"[green]✅ Registered![/green] Welcome, {user['username']}")
        console.print(f" Your User ID: [bold]{user['id']}[/bold]")
    except FortrxAPIError as e:
        console.print(f"[red]❌ Registration failed:[/red] {e.detail}")
        raise typer.Exit(1)