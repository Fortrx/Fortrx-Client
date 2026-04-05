from client.network.api import get,raise_for_status

def fetch_safety_number(other_user_id: int):
    response = get(f"/safety/numbers/{other_user_id}")
    raise_for_status(response,context="fetch_safety_numbers")
    return response.json()

def fetch_user_info(user_id:int):
    response = get(f"/auth/users/{user_id}")
    raise_for_status(response,context="fetch_user_info")
    return response.json()