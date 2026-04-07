import typer
from rich.console import Console
from rich.table import Table

from client.services.messaging import conversation_summaries, refresh_presence_cache, sync_inbox
from client.storage.token_store import load_and_set_token


app = typer.Typer()
console = Console()


@app.command()
def contacts(
    password: str = typer.Option(None, "--password", "-p"),
    sync: bool = typer.Option(True, "--sync/--no-sync"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000),
):
    if not password:
        password = typer.prompt("Storage password", hide_input=True)
    load_and_set_token(password)
    if sync:
        try:
            sync_inbox(password)
            refresh_presence_cache(password)
        except Exception as exc:
            console.print(f"[dim]Offline mode:[/dim] {exc}")

    rows = conversation_summaries(password, limit=limit)
    if not rows:
        console.print("[dim]No local contacts or conversations yet.[/dim]")
        return

    table = Table()
    table.add_column("ID")
    table.add_column("Contact")
    table.add_column("Presence")
    table.add_column("Unread")
    table.add_column("Last Message")
    for row in rows:
        table.add_row(
            str(row["contact_id"]),
            row.get("username") or f"User {row['contact_id']}",
            "online" if row.get("is_online") else "offline",
            str(row.get("unread_count", 0)),
            row.get("last_message_preview") or "",
        )
    console.print(table)
