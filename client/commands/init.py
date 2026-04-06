import typer,base64

from rich.console import Console
from rich.progress import Progress,SpinnerColumn,TextColumn

from client.crypto.keys import generate_identity_keypair,generate_one_time_prekeys,generate_signed_prekey
from client.network.auth import get_me
from client.network.api import FortrxAPIError
from client.network.keys import upload_key_bundle
from client.storage.keystore import save_keys,keys_exist,StorageError
from client.storage.token_store import load_and_set_token
from client.config import settings
from client.crypto.pq_keys import generate_kyber_keypair,sign_kyber_prekey

app = typer.Typer()
console = Console()

def b64(b:bytes):
    return base64.b64encode(b).decode()

@app.command()
def init(
    force: bool = typer.Option(False,"--force"),
    password: str = typer.Option(None,"--password","-p"),
):
    if not load_and_set_token():
        console.print("[red]❌ Login First[/red]")
        raise typer.Exit(1)
    
    if keys_exist() and not force:
        console.print("[yellow]⚠️ Keys already exist.[/yellow]")
        console.print("Use --force to regenerate")
        raise typer.Exit(1)
    
    if not password:
        password = typer.prompt(
            "Storage password",
            hide_input=True,
            confirmation_prompt=True
        )
    try:
        me = get_me()
        user_id = me["id"]
        console.print(f"Initilizing keys for [bold]{me['username']}[/bold]...")
        with Progress(SpinnerColumn(),TextColumn("{task.description}")) as progress:
            task = progress.add_task("Generating identity keypair...",total=None)
            identity = generate_identity_keypair()
            progress.update(task,description="Generating signed prekey...")
            signed_prekey = generate_signed_prekey(identity["signing_private"])
            progress.update(task,description="Generating one-time prekeys...")
            one_time_prekeys = generate_one_time_prekeys(10)
            progress.update(task, description="Generating Kyber768 post-quantum keypair...")
            kyber_keypair = generate_kyber_keypair()
            progress.update(task,description="Signing Kyber prekey with identity key...")
            kyber_signature = sign_kyber_prekey(
                ed25519_signing_private_bytes=identity["signing_private"],
                kyber_public_bytes=kyber_keypair["public"]
            )
            progress.update(task,description="Saving locally...")
        keys_to_save = {
            "user_id":user_id,
            "dh_private":b64(identity["dh_private"]),
            "dh_public": b64(identity["dh_public"]),
            "signing_private": b64(identity["signing_private"]),
            "signing_public": b64(identity["signing_public"]),
            "signed_prekey_private": b64(signed_prekey["private"]),
            "signed_prekey_public": b64(signed_prekey["public"]),
            "signed_prekey_signature": b64(signed_prekey["signature"]),
            "prekey_id": 1,
            "one_time_prekeys": [
                {
                    "private": b64(kp["private"]),
                    "public": b64(kp["public"]),
                }
                for kp in one_time_prekeys
            ]
        }
        keys_to_save.update({
            "kyber_prekey_public":  b64(kyber_keypair["public"]),
            "kyber_prekey_private": b64(kyber_keypair["private"]),
            "kyber_prekey_sig":     b64(kyber_signature)
        })
        save_keys(keys_to_save,password=password)
        upload_key_bundle(
            identity_key = b64(identity["dh_public"]),
            signed_prekey = b64(signed_prekey["public"]),
            signed_prekey_signature= b64(signed_prekey["signature"]),
            prekey_id = 1,
            one_time_prekeys = [b64(kp["public"]) for kp in one_time_prekeys],
            kyber_prekey_public = b64(kyber_keypair["public"]),
            kyber_prekey_signature = b64(kyber_signature)
        )
        console.print("[green]✓ Keys initialized![/green]")
        console.print(f"  Identity key: [dim]{b64(identity['dh_public'])[:20]}...[/dim]")
        console.print(f"  Signed prekey: [dim]{b64(signed_prekey['public'])[:20]}...[/dim]")
        console.print(f"  One-time prekeys uploaded: [bold]10[/bold]")
        console.print("[green]✓ Post-quantum Kyber768 enabled[/green]")
        console.print(f"  Kyber: [dim]{b64(kyber_keypair['public'])[:24]}...[/dim]")
        console.print(f"  Keys saved to: [dim]{settings.KEYS_FILE}[/dim]")
        console.print("[dim]  Private keys never left this device.[/dim]")
    except FortrxAPIError as e:
        console.print(f"[red]❌ Failed:[/red]{e.detail}")
        raise typer.Exit(1)
    except StorageError as e:
        console.print(f"[red]❌ Storage error:[/red]{e}")
        raise typer.Exit(1)