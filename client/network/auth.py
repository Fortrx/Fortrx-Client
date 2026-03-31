from client.network import get,post,raise_for_status,set_token

def register(username:str,email:str,password:str):
    response = post("/auth/register",json={
        "username":username,
        "email":email,
        "password": password
    })
    raise_for_status(response,context="register")
    return response.json()

def login(username:str,password:str):
    response = post("/auth/login",data={
        "username":username,
        "password":password
    },
                    headers={"Content-Type":"application/x-www-form-urlencoded"})
    raise_for_status(response,context="login")
    token = response.json()["access_token"]
    set_token(token)
    return token

def get_me():
    response = get("/auth/me")
    raise_for_status(response,context="get_me")
    return response.json()