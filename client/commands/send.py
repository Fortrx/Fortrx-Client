import typer
from rich.console import Console
from client.services.messaging import send
from client.network.api import FortrxAPIError
from client.storage.token_store import load_and_set_token

app = typer.Typer()
console = Console()

@app.command()
def send_cmd(
    recipient_id: int = typer.Argument(...),
    message: str = typer.Argument(...),
    ttl:int=typer.Option(None,"--ttl"),
    password: str = typer.Option(None,"--password","-p")
):
    load_and_set_token()
    if not password:
        password = typer.prompt("Storage Password",hide_input=True)
    try:
        result = send(
            recipient_id=recipient_id,
            plaintext= message,
            storage_password=password,
            ttl_seconds=ttl
        )
        console.print("[green]✔️ Message send[/green]")
        console.print(f" Message ID: [bold]{result['id']}[/bold]")
        if ttl:
            console.print(f" Expires in: [dim]{ttl}s[/dim]")
    except FortrxAPIError as e:
        console.print(f"[red]❌ Send failed:[/red]{e.detail}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Crypto error:[/red]{e}")
        raise typer.Exit(1)