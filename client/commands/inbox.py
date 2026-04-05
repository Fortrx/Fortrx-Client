import typer
from rich.console import Console
from rich.table import Table
from rich import box
from client.services.messaging import receive
from client.network.api import FortrxAPIError
from client.storage.token_store import load_and_set_token

app = typer.Typer()
console = Console()

@app.command()
def inbox(
    password: str = typer.Option(None,"--password","-p")
):
    load_and_set_token()
    if not password:
        password = typer.prompt("Storage password",hide_input=True)
    try:
        messages = receive(storage_password=password)
    except FortrxAPIError as e:
        console.print(f"[red]❌ Fetch failed:[/red] {e.detail}")
        raise typer.Exit(1)
    if not messages:
        console.print("[dim] No new messages.[/dim]")
        return
    table = Table(box=box.ROUNDED)
    table.add_column("From")
    table.add_column("Msg #")
    table.add_column("Message")
    table.add_column("Status")

    for msg in messages:
        status = "✔️ delivered" if "[" not in msg["plaintext"] else "❌ error"
        table.add_row(
            str(msg["sender_id"]),
            str(msg.get("message_number","?")),
            msg["plaintext"],
            status
        )
    console.print(table)
    console.print(f"\n[dim]{len(messages)} message(s) processed[/dim]")