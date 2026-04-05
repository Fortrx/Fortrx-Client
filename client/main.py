import typer
from client.commands import register, login, send, inbox, verify, init, purge
from client.storage import load_and_set_token

app = typer.Typer(name="fortrx",help="Encrypted Messaging Client")

app.command()(register.register)
app.command()(login.login)
app.command()(send.send_cmd)
app.command()(inbox.inbox)
app.command()(verify.verify)
app.command()(init.init)
app.command()(purge.purge)

#app.add_typer(register.app, name="register")
#app.add_typer(login.app, name="login")
#app.add_typer(send.app, name="send-cmd")
#app.add_typer(inbox.app, name="inbox")
#app.add_typer(verify.app, name="verify")
#app.add_typer(init.app,name="init")
#app.add_typer(purge.app,name="purge")

@app.callback()
def startup():
    load_and_set_token()

if __name__ == "__main__":
    app()