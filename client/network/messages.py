from client.network.api import get, post, delete, raise_for_status


def send_message(
    recipient_id: int,
    sealed_blob: str,
    message_number: int,
    ttl_seconds: int | None = None
) -> dict:

    body = {
        "recipient_id": recipient_id,
        "sealed_blob": sealed_blob,
        "message_number": message_number
    }

    if ttl_seconds is not None:
        body["ttl_seconds"] = ttl_seconds

    response = post("/messages/send", json=body)
    raise_for_status(response, context="send_message")
    return response.json()


def fetch_inbox() -> list[dict]:
    response = get("/messages/inbox")
    raise_for_status(response, context="fetch_inbox")
    return response.json()


def fetch_conversation(other_user_id: int) -> list[dict]:
    response = get(f"/messages/conversation/{other_user_id}")
    raise_for_status(response, context="fetch_conversation")
    return response.json()


def confirm_delivery(message_id: int) -> dict:
    response = delete(f"/messages/{message_id}/confirm")
    raise_for_status(response, context="confirm_delivery")
    return response.json()