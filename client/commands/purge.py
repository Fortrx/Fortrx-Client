import typer
from rich.console import Console
from client.network.messages import fetch_inbox, confirm_delivery
from client.storage.token_store import load_and_set_token

app = typer.Typer()
console = Console()

@app.command()
def purge(
    password: str = typer.Option(None, "--password", "-p")
):
    """Purge all messages in the server inbox by confirming delivery."""
    if not password:
        password = typer.prompt("Storage password", hide_input=True)
    load_and_set_token(password)
    msgs = fetch_inbox()
    if not msgs:
        console.print("[dim]No messages to purge.[/dim]")
        return
    count = 0
    for m in msgs:
        try:
            confirm_delivery(m["id"])
            count += 1
        except Exception as e:
            console.print(f"[red]Failed to purge message {m.get('id')}: {e}[/red]")
    console.print(f"[green]Purged {count} message(s).[/green]")
