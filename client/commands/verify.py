import typer

app = typer.Typer()


@app.command()
def verify(user_id: int):
    print("verify command — wired in C19")