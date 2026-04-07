import typer
from client.commands import chat, contacts, daemon, register, login, send, inbox, verify, init, purge

app = typer.Typer(name="fortrx",help="Encrypted Messaging Client")

app.command()(register.register)
app.command()(login.login)
app.command()(send.send_cmd)
app.command()(inbox.inbox)
app.command()(verify.verify)
app.command()(init.init)
app.command()(purge.purge)
app.command()(chat.chat)
app.command()(contacts.contacts)
app.add_typer(daemon.app, name="daemon")

if __name__ == "__main__":
    app()
