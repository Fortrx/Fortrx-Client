import json
from pathlib import Path
from datetime import datetime

FILE = Path(".fortrx/verified.json")

def load_verifications():
    if not FILE.exists():
        return {}
    return json.loads(FILE.read_text())


def save_verification(user_id: int, safety_number: str):
    data = load_verifications()
    data[str(user_id)] = {
        "safety_number": safety_number,
        "verified_at": datetime.utcnow().isoformat()
    }
    FILE.write_text(json.dumps(data, indent=2))


def is_verified(user_id: int) -> bool:
    data = load_verifications()
    return str(user_id) in data