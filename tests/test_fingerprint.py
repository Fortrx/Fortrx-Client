from client.crypto.fingerprint import generate_safety_number
from client.crypto.keys import generate_identity_keypair


def test_safety_number_is_symmetric_and_distinct_from_halves():
    alice = generate_identity_keypair()
    bob = generate_identity_keypair()

    alice_view = generate_safety_number(
        local_id=1,
        local_ik_public=alice["dh_public"],
        remote_id=2,
        remote_ik_public=bob["dh_public"],
    )
    bob_view = generate_safety_number(
        local_id=2,
        local_ik_public=bob["dh_public"],
        remote_id=1,
        remote_ik_public=alice["dh_public"],
    )

    assert alice_view["safety_number"] == bob_view["safety_number"]
    assert alice_view["safety_number"] != alice_view["your_fingerprint"]
    assert alice_view["safety_number"] != alice_view["their_fingerprint"]


def test_safety_number_changes_when_remote_key_changes():
    alice = generate_identity_keypair()
    bob = generate_identity_keypair()
    impostor = generate_identity_keypair()

    original = generate_safety_number(
        local_id=1,
        local_ik_public=alice["dh_public"],
        remote_id=2,
        remote_ik_public=bob["dh_public"],
    )
    changed = generate_safety_number(
        local_id=1,
        local_ik_public=alice["dh_public"],
        remote_id=2,
        remote_ik_public=impostor["dh_public"],
    )

    assert original["safety_number"] != changed["safety_number"]
