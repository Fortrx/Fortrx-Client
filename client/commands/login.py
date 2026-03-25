import typer

app = typer.Typer()

@app.command()
def login(username:str,password:str):
    print("login command -wired in c2")
    