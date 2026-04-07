import typer
from rich.console import Console
from rich.table import Table

from client.services.messaging import refresh_presence_cache, sync_inbox
from client.storage.db import list_contacts, list_conversation, mark_conversation_viewed
from client.storage.token_store import load_and_set_token


app = typer.Typer()
console = Console()


@app.command()
def chat(
    contact_id: int = typer.Argument(...),
    password: str = typer.Option(None, "--password", "-p"),
    sync: bool = typer.Option(True, "--sync/--no-sync"),
    limit: int = typer.Option(50, "--limit", min=1, max=500),
    before: str = typer.Option(None, "--before", help="Load messages older than this ISO timestamp"),
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

    contacts = {item["user_id"]: item for item in list_contacts(password)}
    contact = contacts.get(contact_id, {})
    from client.network.auth import get_me

    try:
        me = get_me()
        my_id = me["id"]
    except Exception:
        my_id = None
    title = "Saved Messages" if contact_id == my_id else (contact.get("username") or f"User {contact_id}")
    online = contact.get("is_online")

    console.print(f"[bold cyan]Conversation with {title}[/bold cyan]")
    if online is not None:
        console.print(f"[dim]Presence:[/dim] {'online' if online else 'offline'}")

    rows = list_conversation(password, contact_id, limit=limit, before=before)
    if not rows:
        console.print("[dim]No local chat history yet.[/dim]")
        return

    table = Table()
    table.add_column("When")
    table.add_column("Dir")
    table.add_column("Message")
    table.add_column("State")
    for row in rows:
        table.add_row(
            row["created_at"],
            row["direction"],
            row["plaintext"] or "",
            row["status"],
        )
    console.print(table)
    mark_conversation_viewed(password, contact_id)
    if rows:
        console.print(f"\n[dim]Loaded {len(rows)} message(s). Use --before {rows[0]['created_at']} for older history.[/dim]")
