import typer
from client.commands import register, login, send, inbox, verify

app = typer.Typer(name="fortrx",help="Encrypted Messaging Client")

app.command()(register.register)
app.command()(login.login)
app.command()(send.send)
app.command()(inbox.inbox)
app.command()(verify.verify)

if __name__ == "__main__":
    app()