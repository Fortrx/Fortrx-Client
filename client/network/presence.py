from client.network.api import FortrxAPIError, get, post, raise_for_status


def heartbeat(session_id: str) -> dict:
    response = post(
        "/presence/heartbeat",
        json={},
        headers={"X-Client-Session": session_id},
    )
    try:
        raise_for_status(response, context="presence_heartbeat")
    except FortrxAPIError as exc:
        if exc.status_code == 404:
            return {"status": "unsupported", "ttl_seconds": 0}
        raise
    return response.json()


def fetch_presence_contacts() -> list[dict]:
    response = get("/presence/contacts")
    try:
        raise_for_status(response, context="fetch_presence_contacts")
    except FortrxAPIError as exc:
        if exc.status_code == 404:
            return []
        raise
    return response.json()
