import typer
from rich.console import Console
from client.network.messages import fetch_inbox, confirm_delivery
from client.services.messaging import sync_inbox
from client.storage.token_store import load_and_set_token

app = typer.Typer()
console = Console()

@app.command()
def purge(
    password: str = typer.Option(None, "--password", "-p"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete any server-side messages that could not be safely synced.",
    ),
):
    """Drain the server inbox safely. Use --force only for destructive cleanup."""
    if not password:
        password = typer.prompt("Storage password", hide_input=True)
    load_and_set_token(password)
    synced = sync_inbox(password)
    msgs = fetch_inbox()
    if not msgs:
        console.print(f"[green]Inbox drained safely.[/green] Synced {len(synced)} message(s).")
        return
    if not force:
        console.print(
            f"[yellow]{len(msgs)} message(s) remain on the server.[/yellow] "
            "They were not deleted because they are not yet safely persisted locally."
        )
        console.print("[dim]Re-run with --force only if you intentionally want to discard them.[/dim]")
        return
    count = 0
    for m in msgs:
        try:
            confirm_delivery(m["id"])
            count += 1
        except Exception as e:
            console.print(f"[red]Failed to purge message {m.get('id')}: {e}[/red]")
    console.print(f"[green]Purged {count} message(s).[/green]")
