import typer
import json
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from client.network.safety import fetch_safety_number,fetch_user_info
from client.network.api import FortrxAPIError
from client.storage.token_store import load_and_set_token
from client.storage.keystore import load_keys
from client.storage.verification_store import save_verification,load_verifications,is_verified,FILE
from client.crypto.fingerprint import generate_safety_number
from client.config import settings

import base64

app = typer.Typer()
console = Console()

def b64d(data: str):
    return base64.b64decode(data)

def _display_safety_number(
    safety_number: str,
    your_fp,
    their_fp,
    their_username,
    their_id,
    computed_locally
):
    console.print()
    console.print(Panel(
        f"[bold cyan] Safety Number[/bold cyan] with"
        f"[bold] {their_username}[/bold] (ID: {their_id})",
        expand=False
    ))
    console.print()
    numbers = safety_number.split()
    row1 = " ".join(numbers[:3])
    row2 = " ".join(numbers[3:])
    console.print(f" [bold white]{row1}[/bold white]")
    console.print(f" [bold white]{row2}[/bold white]")
    console.print()
    if your_fp and their_fp:
        console.print("[dim]  Your fingerprint half:[/dim]")
        console.print(f"  [cyan]{your_fp}[/cyan]")
        console.print("[dim]  Their fingerprint half:[/dim]")
        console.print(f"  [cyan]{their_fp}[/cyan]")
        console.print()

    if computed_locally:
        console.print("[dim]  ✓ Computed locally[/dim]")
    else:
        console.print("[dim]  ℹ Server-assisted[/dim]")
        console.print("[dim]  Use --local for max security[/dim]")

    console.print()

    console.print(Panel(
        "[yellow]Compare this number with your contact.[/yellow]\n\n"
        "Match → safe\n"
        "Mismatch → MITM",
        border_style="dim"
    ))

    verified = Confirm.ask("Do numbers match?", default=False)

    if verified:
        save_verification(their_id, safety_number)
        console.print(f"[green]✓ Verified {their_username}[/green]")
    else:
        console.print("[yellow]⚠ Not verified[/yellow]")
    
@app.command()
def verify(
    user_id:int,
    password: str = typer.Option(None,"--password","-p"),
    local: bool = typer.Option(False,"--local")
):
    if local:
        if not password:
            password = typer.prompt("Storage password",hide_input=True)
        keys = load_keys(password=password)
        my_id = keys["user_id"]
        my_ik_public = b64d(keys["dh_public"])

        from client.network.keys import fetch_key_bundle
        bundle = fetch_key_bundle(user_id)
        their_ik_public = b64d(bundle["identity_key"])
        safety_number = generate_safety_number(
            local_id=my_id,
            local_ik_public=my_ik_public,
            remote_id=user_id,
            remote_ik_public=their_ik_public
        )
        their_info = fetch_user_info(user_id)
        _display_safety_number(
            safety_number,
            None,
            None,
            their_info["username"],
            user_id,
            True
        )
        return
    load_and_set_token()
    try:
        data = fetch_safety_number(user_id)
        their_info = fetch_user_info(user_id)
        _display_safety_number(
            data["safety_number"],
            data["your_fingerprint"],
            data["their_fingerprint"],
            their_info["username"],
            user_id,
            False
        )
    except FortrxAPIError as e:
        console.print(f"[red]❌ Failed:[/red]{e,detail}")
        raise typer.Exit(1)