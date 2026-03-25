import typer
from client.commands import register, login, send, inbox, verify

app = typer.Typer(name="fortrx",help="Encrypted Messaging Client")

app.add_typer(register.app,name="register")
app.add_typer(login.app,name="login")
app.add_typer(send.app,name="send")
app.add_typer(inbox.app,name="inbox")
app.add_typer(verify.app,name="verify")

if __name__ == "__main__":
    app()