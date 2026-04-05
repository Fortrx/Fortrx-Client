import asyncio
import typer
from datetime import datetime
from rich.console import Console
from client.network.ws import listen
from client.network.auth import get_me
from client.services.messaging import receive_one
from client.storage.token_store import load_and_set_token
from client.network.api import FortrxAPIError
from client.config import settings

app = typer.Typer()
console = Console()

@app.command()
def listen_cmd(
    password: str = typer.Option(None,"--password","-p")
):
    load_and_set_token()
    if not password:
        password = typer.prompt("Storage password",hide_input=True)
    me = get_me()
    user_id = me["id"]
    from client.storage.token_store import load_token
    token = load_token()
    console.print(f"[bold cyan]🏯 Fortrx[/bold cyan] - listening as [bold]{me['username']}[/bold]")
    console.print(f"[dim] Conneted to {settings.SERVER_URL}[/dim]")
    console.print(f"[dim] Press Ctrl+C to disconnect[/dim]\n")
    async def on_message(push_payload: dict):
        try:
            result = await receive_one(push_payload,storage_password=password)
            if result:
                timestamp = datetime.now().strftime("%H:%M:%S")
                console.print(
                    f"[dim]{timestamp}[/dim]"
                    f"[cyan]User {result['sender_id']}[/cyan] → "
                    f"{result['plaintext']}"
                )
                console.print(f"[dim] msg #{result['message_number']} . delivered[/dim]")
        except Exception as e:
            console.print(f"[red]❌ Decrypt error: [/red]{e}")
    try:
        asyncio.run(listen(user_id,on_message,token))
    except KeyboardInterrupt:
        console.print("\n[dim]Disconnected.[/dim]")