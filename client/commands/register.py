import typer
app = typer.Typer()

@app.command()
def register(username: str, email:str , password: str):
    print("register command -wired in C2")
