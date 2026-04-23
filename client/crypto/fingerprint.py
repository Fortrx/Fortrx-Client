import hashlib

def compute_key_fingerprint(
    public_key_bytes:bytes,
    user_id:int,
):
    user_id_bytes = user_id.to_bytes(4,byteorder="big")
    hash_material = public_key_bytes + user_id_bytes
    result = hash_material
    
    for _ in range(5200):
        result = hashlib.sha512(result+hash_material).digest()
    return result[:30]

def fingerprint_to_string(fingerprint_bytes:bytes):
    chunks = []
    for i in range(0,30,5):
        chunk = fingerprint_bytes[i:i+5]
        num = int.from_bytes(chunk,"big")%100000
        chunks.append(f"{num:05d}")
    return " ".join(chunks)

def generate_safety_number(
    local_id:int,
    local_ik_public:bytes,
    remote_id:int,
    remote_ik_public:bytes
):
    local_fp = compute_key_fingerprint(local_ik_public,local_id)
    remote_fp = compute_key_fingerprint(remote_ik_public,remote_id)
    
    if local_id < remote_id:
        combined = local_fp + remote_fp
    else:
        combined = remote_fp + local_fp
    
    # Derive a shared safety number from both participants' fingerprints so it
    # is stable, symmetric, and distinct from either displayed fingerprint half.
    safety_material = hashlib.sha512(combined).digest()[:30]
    safety_number = fingerprint_to_string(safety_material)

    return {
        "safety_number": safety_number,
        "your_fingerprint": fingerprint_to_string(local_fp),
        "their_fingerprint": fingerprint_to_string(remote_fp),
    }
