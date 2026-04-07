import typer
from rich.console import Console
from rich.table import Table
from rich import box
from client.services.messaging import conversation_summaries, refresh_presence_cache, sync_inbox
from client.storage.db import mark_all_conversations_viewed
from client.storage.token_store import load_and_set_token

app = typer.Typer()
console = Console()

@app.command()
def inbox(
    password: str = typer.Option(None,"--password","-p"),
    sync: bool = typer.Option(True, "--sync/--no-sync")
):
    if not password:
        password = typer.prompt("Storage password",hide_input=True)
    load_and_set_token(password)
    if sync:
        try:
            sync_inbox(password)
            refresh_presence_cache(password)
        except Exception as exc:
            console.print(f"[dim]Offline mode:[/dim] {exc}")
    conversations = conversation_summaries(password, limit=100)
    if not conversations:
        console.print("[dim] No local conversations.[/dim]")
        return
    table = Table(box=box.ROUNDED)
    table.add_column("Contact")
    table.add_column("Presence")
    table.add_column("Last Dir")
    table.add_column("Last Message")
    table.add_column("Status")
    table.add_column("Unread")

    for convo in conversations:
        title = convo.get("username") or f"User {convo['contact_id']}"
        status = convo.get("last_status") or "stored"
        table.add_row(
            title,
            "online" if convo.get("is_online") else "offline",
            convo.get("last_direction") or "",
            convo.get("last_message_preview") or "",
            status,
            str(convo.get("unread_count", 0)),
        )
    console.print(table)
    mark_all_conversations_viewed(password)
    console.print(f"\n[dim]{len(conversations)} conversation(s)[/dim]")
