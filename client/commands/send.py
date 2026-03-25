import typer
app = typer.Typer()
@app.command()
def send(recipient_id: int, message: str):
    print("send command --wired in c16")