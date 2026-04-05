# FORTRX COMPLETE ECOSYSTEM MAP

**Scope**: Complete Fortrx encrypted messaging system  
**Components**: Fortress Server + Fortrx-Client  
**Language**: Python 3.9+  
**Protocol**: Signal Protocol (X3DH + Double Ratchet)  
**Storage**: PostgreSQL/SQLite + S3/MinIO + Redis  
**Architecture**: REST API (FastAPI) + CLI Client (Typer)

---

## TABLE OF CONTENTS

1. **FORTRESS SERVER** (app/)
2. **FORTRX CLIENT** (client/)
3. **INTEGRATION FLOW** (Client ↔ Server)
4. **DATABASE SCHEMA**
5. **API ENDPOINTS**
6. **ALL MODULES & FUNCTIONS**

---

# PART 1: FORTRESS SERVER

## SERVER ENTRY POINT

### `run.py`
```
Main script that initializes the CLI application
├─ Imports: client.main.app
└─ Function: __main__ → app()
```

---

## CORE APPLICATION STRUCTURE

### `client/main.py` - CLI Application Root
```
Entry point for the Typer CLI application

Variables:
  app: typer.Typer - Main CLI app with name="fortrx"

Functions:
  startup() - Callback executed on every command
    └─ Loads token from disk via load_and_set_token()
    
Registered Commands (7 total):
  1. register.register()     - User registration
  2. login.login()           - User authentication
  3. send.send_cmd()         - Send encrypted message
  4. inbox.inbox()           - Fetch and decrypt inbox
  5. verify.verify()         - Verify user (stub)
  6. init.init()             - Initialize cryptographic keys
  7. purge.purge()           - Delete all server messages
```

### `client/config.py` - Settings & Configuration
```
Configuration management using Pydantic

Class: Settings(BaseSettings)
  ├─ SERVER_URL: str = "http://localhost:8000"
  ├─ LOCAL_STORAGE_PATH: str = ".fortrx"
  ├─ TOKEN_FILE: str = ".fortrx/token"
  ├─ KEYS_FILE: str = ".fortrx/keys.enc"
  ├─ SESSION_FILE: str = '.fortrx/sessions.enc'
  ├─ STORAGE_PASSWORD: str = ""

Instance:
  settings = Settings() - Global singleton
```

---

## COMMAND MODULES

### `client/commands/register.py` - User Registration
```
Module: Handles new user registration

Functions:
  ├─ register(
  │    username: str (Argument),
  │    email: str (Argument),
  │    password: str (Option, hidden)
  │  ) → None
  │  
  │  Flow:
  │  ├─ Calls: network.auth.register_user(username, email, password)
  │  ├─ Returns: {"username", "id", ...}
  │  ├─ Output: Success message to console
  │  └─ On Error: Catches FortrxAPIError, prints error, exits(1)

Dependencies:
  └─ client.network.auth.register_user()
```

### `client/commands/login.py` - User Authentication
```
Module: Handles user login and session persistence

Functions:
  ├─ login(
  │    username: str (Argument),
  │    password: str (Option, hidden)
  │  ) → None
  │
  │  Flow:
  │  ├─ Calls: network.auth.login_user(username, password)
  │  │         → Returns access token
  │  ├─ Calls: network.auth.get_me()
  │  │         → Returns user info {"username", "id", ...}
  │  ├─ Calls: storage.token_store.save_token(token)
  │  │         → Persists token to disk for future use
  │  ├─ Output: Login success with user ID
  │  └─ On Error: FortrxAPIError handling

Dependencies:
  ├─ client.network.auth.login_user()
  ├─ client.network.auth.get_me()
  └─ client.storage.save_token()
```

### `client/commands/send.py` - Send Encrypted Message
```
Module: Sends encrypted E2E messages

Functions:
  ├─ send_cmd(
  │    recipient_id: int (Argument),
  │    message: str (Argument),
  │    ttl: int (Option, optional),
  │    password: str (Option, hidden)
  │  ) → None
  │
  │  Encryption Flow:
  │  ├─ Loads token → load_and_set_token()
  │  ├─ Prompts for storage password if not provided
  │  ├─ Calls: services.messaging.send(
  │  │            recipient_id,
  │  │            plaintext=message,
  │  │            storage_password,
  │  │            ttl_seconds=ttl
  │  │          )
  │  │  └─ Returns: {"id", ...}
  │  ├─ Output: Message sent with ID
  │  └─ On Error: FortrxAPIError or crypto error handling

Dependencies:
  ├─ client.storage.token_store.load_and_set_token()
  └─ client.services.messaging.send()
```

### `client/commands/inbox.py` - Fetch & Display Messages
```
Module: Retrieves and displays decrypted messages

Functions:
  ├─ inbox(
  │    password: str (Option, hidden)
  │  ) → None
  │
  │  Decryption Flow:
  │  ├─ Loads token → load_and_set_token()
  │  ├─ Prompts for storage password if not provided
  │  ├─ Calls: services.messaging.receive(storage_password)
  │  │         → Returns list of decrypted messages
  │  ├─ Renders Table:
  │  │  ├─ Columns: From | Msg # | Message | Status
  │  │  ├─ Row format: sender_id | message_number | plaintext | ✔️/❌
  │  │  └─ Display count of processed messages
  │  └─ On Error: FortrxAPIError handling

Dependencies:
  ├─ client.storage.token_store.load_and_set_token()
  └─ client.services.messaging.receive()
```

### `client/commands/init.py` - Initialize Cryptographic Keys
```
Module: Generates and uploads cryptographic key bundle

Functions:
  ├─ init(
  │    force: bool (Option, default=False),
  │    password: str (Option, hidden)
  │  ) → None
  │
  │  Key Generation Flow:
  │  ├─ Checks: load_and_set_token() → Must be logged in
  │  ├─ Checks: keys_exist() → Fails if keys exist (unless --force)
  │  ├─ Generates:
  │  │  ├─ Identity keypair:
  │  │  │   ├─ X25519 DH keypair (dh_private, dh_public)
  │  │  │   └─ Ed25519 signing keypair (signing_private, signing_public)
  │  │  │
  │  │  ├─ Signed Prekey:
  │  │  │   ├─ X25519 key pair
  │  │  │   ├─ Ed25519 signature of public key
  │  │  │   └─ Generated via: crypto.keys.generate_signed_prekey()
  │  │  │
  │  │  └─ One-Time Prekeys:
  │  │      ├─ 10x X25519 keypairs
  │  │      └─ Generated via: crypto.keys.generate_one_time_prekeys(10)
  │  │
  │  ├─ Saves Locally:
  │  │  ├─ Calls: storage.keystore.save_keys(keys_dict, password)
  │  │  └─ Stores in: .fortrx/keys_{user_id}.enc (encrypted)
  │  │
  │  ├─ Uploads to Server:
  │  │  ├─ Calls: network.keys.upload_key_bundle(...)
  │  │  └─ Sends public key data only
  │  │
  │  └─ Output: Success with key hashes, file location
  │     On Error: FortrxAPIError or StorageError

Dependencies:
  ├─ client.storage.token_store.load_and_set_token()
  ├─ client.network.auth.get_me()
  ├─ client.crypto.keys.generate_identity_keypair()
  ├─ client.crypto.keys.generate_signed_prekey()
  ├─ client.crypto.keys.generate_one_time_prekeys()
  ├─ client.storage.keystore.save_keys()
  ├─ client.storage.keystore.keys_exist()
  └─ client.network.keys.upload_key_bundle()
```

### `client/commands/verify.py` - User Verification (Stub)
```
Functions:
  └─ verify(user_id: int) → None
     └─ Prints: "verify command — wired in C19"
     └─ Status: NOT IMPLEMENTED
```

### `client/commands/purge.py` - Delete All Server Messages
```
Module: Confirms delivery (purges) all messages in server inbox

Functions:
  ├─ purge() → None
  │
  │  Flow:
  │  ├─ Loads token → load_and_set_token()
  │  ├─ Fetches inbox → network.messages.fetch_inbox()
  │  │               → Returns list of messages
  │  ├─ For each message:
  │  │  └─ Calls: network.messages.confirm_delivery(msg_id)
  │  │           → Deletes from server
  │  └─ Output: Count of purged messages

Dependencies:
  ├─ client.storage.token_store.load_and_set_token()
  ├─ client.network.messages.fetch_inbox()
  └─ client.network.messages.confirm_delivery()
```

---

## NETWORK MODULE

### `client/network/api.py` - Base HTTP Client
```
Module: Low-level HTTP communication with server

Global State:
  _token: str | None - Current authentication token

Functions:
  ├─ set_token(token: str) → None
  │  └─ Sets global _token
  │
  ├─ get_token() → str | None
  │  └─ Retrieves global _token
  │
  ├─ _headers() → dict
  │  └─ Returns: {"Authorization": "Bearer {_token}"} if token exists
  │
  ├─ get(endpoint: str, **kwargs) → httpx.Response
  │  ├─ url = settings.SERVER_URL + endpoint
  │  └─ Returns httpx.get(url, headers=_headers(), **kwargs)
  │
  ├─ post(endpoint: str, json: dict, data: dict, **kwargs) → httpx.Response
  │  ├─ url = settings.SERVER_URL + endpoint
  │  └─ Returns httpx.post(..., json, data, headers, **kwargs)
  │
  ├─ delete(endpoint: str, **kwargs) → httpx.Response
  │  └─ Returns httpx.delete(url, headers=_headers(), **kwargs)
  │
  └─ raise_for_status(response: httpx.Response, context: str) → None | Raises
     ├─ If status_code >= 400:
     │  ├─ Parses response.json()["detail"] or response.text
     │  └─ Raises FortrxAPIError(status_code, detail, context)

Exception:
  class FortrxAPIError(Exception)
    ├─ __init__(status_code: int, detail: str, context: str)
    ├─ self.status_code
    ├─ self.detail
    ├─ self.context
    └─ Message format: "[{status_code}]{context}:{detail}"
```

### `client/network/auth.py` - Authentication Endpoints
```
Module: Handles auth-related API calls

Functions:
  ├─ register(username: str, email: str, password: str) → dict
  │  ├─ Endpoint: POST /auth/register
  │  ├─ Payload: {"username", "email", "password"}
  │  ├─ Calls: api.post() → api.raise_for_status()
  │  └─ Returns: User object {"id", "username", "email", ...}
  │
  ├─ login(username: str, password: str) → str (token)
  │  ├─ Endpoint: POST /auth/login
  │  ├─ Payload: form-encoded {"username", "password"}
  │  ├─ Calls: api.post(headers={"Content-Type": "application/x-www-form-urlencoded"})
  │  ├─ Calls: api.set_token(token)
  │  ├─ Returns: access_token string
  │  └─ Side Effect: Sets global token in api.py
  │
  └─ get_me() → dict
     ├─ Endpoint: GET /auth/me
     ├─ Calls: api.get() → api.raise_for_status()
     └─ Returns: Current user object {"id", "username", "email", ...}
```

### `client/network/keys.py` - Key Bundle Management
```
Module: Upload and fetch cryptographic key bundles

Functions:
  ├─ upload_key_bundle(
  │    identity_key: str (b64),
  │    signed_prekey: str (b64),
  │    signed_prekey_signature: str (b64),
  │    prekey_id: int,
  │    one_time_prekeys: list[str] (b64)
  │  ) → dict
  │
  │  ├─ Endpoint: POST /keys/upload
  │  ├─ Payload: All 5 parameters (base64 encoded)
  │  ├─ Calls: api.post() → api.raise_for_status()
  │  └─ Returns: Server response {"status", ...}
  │
  └─ fetch_key_bundle(user_id: int) → dict
     ├─ Endpoint: GET /keys/{user_id}
     ├─ Calls: api.get() → api.raise_for_status()
     └─ Returns: User's key bundle {
                    "identity_key": str (b64),
                    "signed_prekey": str (b64),
                    "signed_prekey_signature": str (b64),
                    "prekey_id": int,
                    "one_time_prekey": str (b64) | None
                  }
```

### `client/network/messages.py` - Message Operations
```
Module: Send and retrieve encrypted messages

Functions:
  ├─ send_message(
  │    recipient_id: int,
  │    sealed_blob: str (b64),
  │    message_number: int,
  │    ttl_seconds: int | None
  │  ) → dict
  │
  │  ├─ Endpoint: POST /messages/send
  │  ├─ Payload: {"recipient_id", "sealed_blob", "message_number", "ttl_seconds"}
  │  ├─ Calls: api.post() → api.raise_for_status()
  │  └─ Returns: {"id", "status", ...}
  │
  ├─ fetch_inbox() → list[dict]
  │  ├─ Endpoint: GET /messages/inbox
  │  ├─ Calls: api.get() → api.raise_for_status()
  │  └─ Returns: List of message objects {
  │                "id": int,
  │                "sender_id": int,
  │                "sealed_blob": str (b64),
  │                "message_number": int,
  │                ...
  │              }
  │
  ├─ fetch_conversation(other_user_id: int) → list[dict]
  │  ├─ Endpoint: GET /messages/conversation/{other_user_id}
  │  ├─ Calls: api.get() → api.raise_for_status()
  │  └─ Returns: List of all messages with other_user_id
  │
  └─ confirm_delivery(message_id: int) → dict
     ├─ Endpoint: DELETE /messages/{message_id}/confirm
     ├─ Calls: api.delete() → api.raise_for_status()
     └─ Returns: Deletion confirmation {"status", ...}
```

### `client/network/ws.py`
```
Status: EMPTY FILE (WebSocket support planned but not implemented)
```

---

## CRYPTOGRAPHY MODULE

### `client/crypto/keys.py` - Key Generation
```
Module: X25519/Ed25519 key generation utilities

Functions:
  ├─ generate_identity_keypair() → dict
  │  ├─ Generates X25519 DH keypair:
  │  │   ├─ dh_private: X25519PrivateKey → raw bytes
  │  │   └─ dh_public: X25519PublicKey → raw bytes
  │  │
  │  ├─ Generates Ed25519 signing keypair:
  │  │   ├─ signing_private: Ed25519PrivateKey → raw bytes
  │  │   └─ signing_public: Ed25519PublicKey → raw bytes
  │  │
  │  └─ Returns: {
  │       "dh_private": bytes,
  │       "dh_public": bytes,
  │       "signing_private": bytes,
  │       "signing_public": bytes
  │     }
  │
  ├─ generate_signed_prekey(signing_private_key_bytes: bytes) → dict
  │  ├─ Input: Ed25519 signing private key (raw bytes)
  │  ├─ Generates X25519 prekey pair
  │  ├─ Signs the prekey public key using signing_private
  │  └─ Returns: {
  │       "private": bytes (X25519 private),
  │       "public": bytes (X25519 public),
  │       "signature": bytes (Ed25519 signature)
  │     }
  │
  ├─ generate_one_time_prekeys(count: int = 10) → list[dict]
  │  ├─ Generates 'count' X25519 keypairs
  │  └─ Returns: [{
  │       "private": bytes,
  │       "public": bytes
  │     }, ...] × count
  │
  ├─ encode_public_key(raw_bytes: bytes) → str
  │  └─ Returns: base64 encoded key
  │
  └─ decode_public_key(b64_str: str) → bytes
     └─ Returns: decoded raw bytes
```

### `client/crypto/x3dh.py` - X3DH Key Agreement (Signal Protocol)
```
Module: Extended Triple Diffie-Hellman key agreement

Constants/Helpers:
  └─ _hkdf_derive(input_bytes: bytes) → bytes
     ├─ HKDF(SHA256, length=32, salt=b"\x00"*32, info="Fortrx X3DH")
     └─ Returns: 32-byte derived key

Functions:
  ├─ x3dh_sender(
  │    ik_a_private: bytes (Alice's identity private),
  │    ik_b_public: bytes (Bob's identity public),
  │    spk_b_public: bytes (Bob's signed prekey public),
  │    opk_b_public: bytes | None (Bob's optional one-time prekey)
  │  ) → dict
  │
  │  Algorithm (Signal Protocol):
  │  ├─ Generate ephemeral keypair: ek_a_private, ek_a_public
  │  ├─ Perform 3-4 DH operations:
  │  │  ├─ dh1 = ik_a.exchange(spk_b)
  │  │  ├─ dh2 = ek_a.exchange(ik_b)
  │  │  ├─ dh3 = ek_a.exchange(spk_b)
  │  │  └─ dh4 = ek_a.exchange(opk_b) [if opk_b provided]
  │  ├─ Concatenate all DH outputs
  │  ├─ Derive shared_secret via _hkdf_derive()
  │  │
  │  └─ Returns: {
  │       "shared_secret": bytes (32),
  │       "ek_public": bytes (ephemeral public key)
  │     }
  │
  └─ x3dh_receiver(
     ik_b_private: bytes (Bob's identity private),
     spk_b_private: bytes (Bob's signed prekey private),
     ik_a_public: bytes (Alice's identity public),
     ek_a_public: bytes (Alice's ephemeral public),
     opk_b_private: bytes | None (Bob's one-time prekey private if used)
   ) → bytes (shared_secret)

   Algorithm (Signal Protocol - Receiver Side):
   ├─ Perform 3-4 DH operations (inverse of sender):
   │  ├─ dh1 = spk_b.exchange(ik_a)
   │  ├─ dh2 = ik_b.exchange(ek_a)
   │  ├─ dh3 = spk_b.exchange(ek_a)
   │  └─ dh4 = opk_b.exchange(ek_a) [if opk_b provided]
   ├─ Concatenate all DH outputs
   └─ Returns: Derived shared_secret (same as sender's)

   Signal Protocol Property: Both parties derive identical shared_secret
```

### `client/crypto/ratchet.py` - Double Ratchet Algorithm
```
Module: Message encryption with forward secrecy (Signal Protocol)

Dataclass: RatchetState
  ├─ root_key: bytes (32) - Root key for DH ratchet
  ├─ sending_chain_key: bytes (32) - Current sending chain key
  ├─ recv_chain_key: bytes (32) - Current receiving chain key
  ├─ dh_sending_private: bytes (32) - Our current DH private
  ├─ dh_sending_public: bytes (32) - Our current DH public
  ├─ dh_remote_public: bytes (32) - Remote party's current DH public
  ├─ send_count: int - Messages sent in this phase
  ├─ recv_count: int - Messages received in this phase
  └─ skipped_message_keys: dict - Out-of-order message key cache

Helper Functions:
  ├─ _hkdf(salt: bytes, input_key: bytes) → tuple(key, chain)
  │  └─ HKDF-SHA256 deriving 64 bytes (32 key + 32 chain)
  │
  ├─ _gen_dh_keypair() → tuple(priv: bytes, pub: bytes)
  │  └─ Generate new X25519 keypair
  │
  └─ _dh(priv_bytes: bytes, pub_bytes: bytes) → bytes
     └─ Perform X25519 key exchange

Initialization Functions:
  ├─ init_ratchet_sender(
  │    shared_secret: bytes (from X3DH),
  │    recipient_ratchet_public: bytes (recipient's ratchet key)
  │  ) → RatchetState
  │
  │  ├─ Generate initial DH keypair
  │  ├─ Perform DH with recipient's ratchet key
  │  ├─ Apply HKDF to derive root_key and sending_chain_key
  │  └─ Return initialized state
  │
  └─ init_ratchet_receiver(
     shared_secret: bytes,
     our_ratchet_private: bytes (our ratchet key)
   ) → RatchetState

     ├─ Start with shared_secret as root_key
     ├─ Initialize send_chain = 0x00 (unused until rotation)
     └─ Return initialized state

Encryption/Decryption:
  ├─ derive_message_key(chain_key: bytes) → tuple(msg_key, next_chain)
  │  ├─ msg_key = HMAC-SHA256(chain_key, b"\x01")
  │  ├─ next_chain = HMAC-SHA256(chain_key, b"x02")
  │  └─ Returns: (msg_key, next_chain)
  │
  ├─ dh_ratchet_step(state: RatchetState, their_new_public: bytes) → RatchetState
  │  ├─ Called when receiving message with new DH public key
  │  ├─ Performs DH with remote's new public key
  │  ├─ Applies HKDF twice (once for recv, once for send)
  │  ├─ Resets chain counters to 0
  │  ├─ Clears skipped_message_keys
  │  └─ Updates state with new DH keypair
  │
  ├─ ratchet_encrypt(state: RatchetState, plaintext: bytes) → tuple(header, ciphertext)
  │  ├─ Derive message key from sending_chain_key
  │  ├─ Advance sending_chain_key
  │  ├─ Increment send_count
  │  ├─ Encrypt plaintext with AES-256-GCM using message key
  │  ├─ Header = {"dh_public": b64(our_dh_public), "send_count", "recv_count"}
  │  └─ Returns: (header_dict, nonce[12] + ciphertext)
  │
  └─ ratchet_decrypt(state: RatchetState, header: dict, ciphertext: bytes) → bytes
     ├─ Extract remote's DH public from header
     ├─ If DH public changed:
     │  └─ Perform dh_ratchet_step()
     ├─ If message is out-of-order (recv_count > send_count):
     │  ├─ Check skipped_message_keys cache
     │  └─ Use cached key if available, else raise error
     ├─ Advance recv_chain_key to match sender's send_count
     │  ├─ Store intermediate message keys for future out-of-order arrivals
     │  └─ Track in skipped_message_keys
     ├─ Decrypt ciphertext with AES-256-GCM
     └─ Returns: plaintext bytes
```

### `client/crypto/sealed_sender.py` - Anonymous Sender Encryption
```
Module: Seal identity and ciphertext for privacy (Signal Protocol)

Functions:
  ├─ _json_safe(obj) → JSON-serializable object
  │  └─ Recursively encodes bytes to base64, handles objects with public_bytes()
  │
  ├─ seal(
  │    sender_id: int,
  │    sender_ik_public: bytes,
  │    recipient_ik_public: bytes,
  │    ciphertext: bytes,
  │    header: dict
  │  ) → bytes (sealed_blob)
  │
  │  Flow:
  │  ├─ Generate ephemeral keypair: ek_private, ek_public
  │  ├─ Perform ECDH with recipient's identity key
  │  ├─ Derive encryption key via HKDF(SHA256, info="Fortrx Sealed Sender")
  │  ├─ Create inner JSON:
  │  │  {
  │  │    "sender_id": int,
  │  │    "sender_ik_public": b64(sender_ik_public),
  │  │    "ciphertext": b64(ciphertext),
  │  │    "header": header_dict_safe
  │  │  }
  │  ├─ Encrypt inner JSON with AES-256-GCM
  │  │  └─ nonce = random 12 bytes
  │  └─ Returns: ek_public[32] + nonce[12] + encrypted_inner
  │             (Total: 44+ bytes)
  │
  └─ unseal(
     recipient_ik_private: bytes,
     sealed_blob: bytes
   ) → dict (inner object)

     ├─ Extract components:
     │  ├─ ek_public = first 32 bytes
     │  ├─ nonce = next 12 bytes
     │  └─ encrypted_inner = remaining bytes
     ├─ Perform ECDH to recover encryption key
     ├─ Decrypt inner JSON with AES-256-GCM
     └─ Returns: Parsed JSON object with sender info and ciphertext
```

---

## SERVICES MODULE

### `client/services/messaging.py` - High-Level Messaging
```
Module: Orchestrates full end-to-end messaging (X3DH + Ratchet + Sealed Sender)

Helper Functions:
  ├─ b64e(data: bytes) → str
  │  └─ Returns: base64 encoded string
  │
  └─ b64d(data: str) → bytes
     └─ Returns: decoded bytes

  ├─ encode_header(obj) → JSON-safe object
  │  └─ Recursively encodes bytes to base64

Functions:
  ├─ send(
  │    recipient_id: int,
  │    plaintext: str,
  │    storage_password: str,
  │    ttl_seconds: int | None = None
  │  ) → dict (server response)
  │
  │  Complete Encryption Pipeline:
  │  ├─ Step 1: Load local keys
  │  │  └─ load_keys(password) → {user_id, dh_private, dh_public, ...}
  │  │
  │  ├─ Step 2: Check for existing session with recipient
  │  │  └─ load_session(recipient_id, password)
  │  │  └─ If exists, verify recipient's keys haven't changed
  │  │
  │  ├─ Step 3: If new session, do X3DH
  │  │  ├─ fetch_key_bundle(recipient_id) → {identity_key, signed_prekey, ...}
  │  │  ├─ Call: crypto.x3dh.x3dh_sender(...) → {shared_secret, ek_public}
  │  │  ├─ Call: crypto.ratchet.init_ratchet_sender(...)
  │  │  └─ Store X3DH data in ratchet state header
  │  │
  │  ├─ Step 4: Encrypt with Double Ratchet
  │  │  ├─ Call: crypto.ratchet.ratchet_encrypt(state, plaintext)
  │  │  └─ Returns: (header_dict, nonce+ciphertext)
  │  │
  │  ├─ Step 5: Seal with anonymous sender encryption
  │  │  ├─ Call: crypto.sealed_sender.seal(...)
  │  │  └─ Returns: sealed_blob (bytes)
  │  │
  │  ├─ Step 6: Send to server
  │  │  ├─ Call: network.messages.api_send(
  │  │  │         recipient_id,
  │  │  │         sealed_blob=b64(sealed_blob),
  │  │  │         message_number=state.send_count,
  │  │  │         ttl_seconds
  │  │  │       )
  │  │  └─ Returns: {id, ...}
  │  │
  │  ├─ Step 7: Save updated session state
  │  │  └─ save_session(recipient_id, state, password)
  │  │
  │  └─ Returns: API response with message_id
  │
  └─ receive(storage_password: str) → list[dict]
     
     Complete Decryption Pipeline:
     ├─ Step 1: Load local keys
     │  ├─ load_keys(password) → {..., dh_private, signed_prekey_private, ...}
     │  └─ Build OTP key lookup: {public: private}
     │
     ├─ Step 2: Fetch messages from server
     │  └─ network.messages.fetch_inbox() → list of sealed messages
     │
     ├─ Step 3: For each message:
     │  ├─ Step 3a: Unseal to get sender info
     │  │  ├─ Call: crypto.sealed_sender.unseal(my_ik_private, sealed_blob)
     │  │  └─ Returns: {sender_id, sender_ik_public, ciphertext, header}
     │  │
     │  ├─ Step 3b: Check for X3DH initialization (new session)
     │  │  ├─ If x3dh_data in header:
     │  │  │  ├─ Extract ek_public, otpk_used, otpk_public
     │  │  │  ├─ Call: crypto.x3dh.x3dh_receiver(...)
     │  │  │  ├─ Call: crypto.ratchet.init_ratchet_receiver(shared_secret)
     │  │  │  └─ New session initialized
     │  │  │
     │  │  └─ Else (existing session):
     │  │     ├─ Call: load_session(sender_id, password)
     │  │     └─ If None: log "[session lost - cannot decrypt]"
     │  │
     │  ├─ Step 3c: Decrypt with Double Ratchet
     │  │  ├─ Call: crypto.ratchet.ratchet_decrypt(state, header, ciphertext)
     │  │  └─ Returns: plaintext_bytes
     │  │
     │  ├─ Step 3d: Save updated session
     │  │  └─ save_session(sender_id, state, password)
     │  │
     │  ├─ Step 3e: Confirm delivery on server
     │  │  └─ network.messages.confirm_delivery(msg_id)
     │  │
     │  └─ Step 3f: Append to results
     │     └─ {sender_id, plaintext, message_id, message_number}
     │
     └─ Returns: List of successfully decrypted messages
```

---

## STORAGE MODULE

### `client/storage/keystore.py` - Encrypted Key Storage
```
Module: Persist cryptographic keys with password-based encryption

Helpers:
  ├─ _derive_key(password: str, salt: bytes) → bytes (32)
  │  └─ PBKDF2-HMAC-SHA256(iterations=480000) with provided salt
  │
  ├─ _encrypt(data: bytes, password: str) → bytes
  │  ├─ Generate salt (16 bytes) and nonce (12 bytes)
  │  ├─ Derive key from password and salt
  │  ├─ Encrypt with AES-256-GCM
  │  └─ Returns: salt + nonce + ciphertext
  │
  └─ _decrypt(data: bytes, password: str) → bytes
     ├─ Extract salt, nonce, ciphertext
     ├─ Derive key and decrypt
     └─ On failure: Raises StorageError("Wrong password or corrupted file")

Functions:
  ├─ save_keys(keys: dict, password: str = None) → None
  │  ├─ password = password or settings.STORAGE_PASSWORD
  │  ├─ Creates directory: settings.LOCAL_STORAGE_PATH
  │  ├─ Serializes keys dict to JSON
  │  ├─ Encrypts with _encrypt()
  │  ├─ Saves to: .fortrx/keys_{user_id}.enc (per-user file)
  │  └─ Also saves to: .fortrx/keys.enc (legacy compatibility)
  │
  ├─ load_keys(password: str = None) → dict
  │  ├─ Tries to load per-user file: .fortrx/keys_{current_user}.enc
  │  ├─ Falls back to legacy: .fortrx/keys.enc
  │  ├─ Falls back to any single keys_*.enc if exactly one exists
  │  ├─ Decrypts with _decrypt()
  │  ├─ Parses JSON
  │  └─ Returns: { user_id, dh_private (b64), dh_public, signing_private,
  │               signing_public, signed_prekey_*, one_time_prekeys: [...] }
  │
  ├─ keys_exist() → bool
  │  └─ Checks if any encrypted key file exists
  │
  └─ load_keys_or_exit(password: str = None) → dict | Exits
     └─ Wrapper that catches StorageError and exits process
```

### `client/storage/session_store.py` - Session Persistence
```
Module: Persist encryption session state between messages

Dataclass/Structures:
  └─ References: RatchetState from crypto.ratchet

Serialization Helpers:
  ├─ _b64e(b: bytes | None) → str | None
  │  └─ Base64 encode if not None
  │
  └─ _b64d(s: str | None) → bytes | None
     └─ Base64 decode if not None

Functions:
  ├─ serialize_state(state: RatchetState) → dict
  │  └─ Converts RatchetState to JSON-serializable dict (all bytes → b64):
  │     {
  │       "root_key": b64,
  │       "sending_chain_key": b64,
  │       "recv_chain_key": b64,
  │       "dh_sending_private": b64,
  │       "dh_sending_public": b64,
  │       "dh_remote_public": b64,
  │       "recipient_ik_public": b64,
  │       "send_count": int,
  │       "recv_count": int
  │     }
  │
  ├─ deserialize_state(data: dict) → RatchetState
  │  └─ Reconstructs RatchetState from serialized dict
  │
  ├─ save_sessions(sessions: dict, password: str = None) → None
  │  ├─ sessions format: {str(user_id): serialized_state_dict, ...}
  │  ├─ path: settings.SESSION_FILE (.fortrx/sessions.enc)
  │  ├─ Serializes to JSON, encrypts with keystore._encrypt()
  │  └─ Writes encrypted bytes to file
  │
  ├─ load_sessions(password: str = None) → dict
  │  ├─ Loads encrypted sessions file
  │  ├─ Decrypts and parses JSON
  │  └─ Returns: {str(user_id): serialized_state, ...}
  │
  ├─ save_session(other_user_id: int, state: RatchetState, password: str) → None
  │  ├─ Loads all sessions
  │  ├─ Updates sessions[str(other_user_id)] with serialized_state
  │  └─ Saves all sessions
  │
  └─ load_session(other_user_id: int, password: str = None) → RatchetState | None
     ├─ Loads all sessions
     ├─ If str(other_user_id) in sessions:
     │  └─ Returns deserialized state
     └─ Else returns None
```

### `client/storage/token_store.py` - Authentication Token Storage
```
Module: Persist JWT authentication token

Functions:
  ├─ save_token(token: str) → None
  │  ├─ path: settings.TOKEN_FILE (.fortrx/token)
  │  ├─ Creates directory if needed
  │  └─ Writes token as plain text to file
  │     ⚠️ Note: Plain text file (not encrypted)
  │
  ├─ load_token() → str | None
  │  ├─ path: settings.TOKEN_FILE
  │  └─ Returns stripped token or None if file doesn't exist
  │
  ├─ delete_token() → None
  │  └─ Deletes token file if it exists
  │
  └─ load_and_set_token() → bool
     ├─ Loads token from disk
     ├─ Calls: network.api.set_token(token) if token exists
     └─ Returns: True if token was set, False otherwise
```

---

## TEST MODULES

### `tests/test_encoding.py`
```
Module: Tests for session serialization and sealing/unsealing

Test Functions:
  ├─ test_session_serialize_deserialize_roundtrip()
  │  ├─ Creates dummy RatchetState with test values
  │  ├─ Serializes to dict via session_store.serialize_state()
  │  ├─ Deserializes back via session_store.deserialize_state()
  │  └─ Asserts: root_key, dh_sending_public, recipient_ik_public match
  │
  └─ test_seal_unseal_roundtrip()
     ├─ Generates X25519 recipient keypair
     ├─ Generates X25519 sender keypair
     ├─ Calls: crypto.sealed_sender.seal(...)
     ├─ Calls: crypto.sealed_sender.unseal(...)
     ├─ Asserts: Decrypted ciphertext and sender public match
```

### `tests/test_ratchet.py`
```
Module: Tests for ratchet encryption/decryption

Helper:
  └─ make_state_with_chain(chain_key: bytes, dh_pub: bytes) → RatchetState
     └─ Creates minimal RatchetState for testing

Test Functions:
  ├─ test_derive_message_key_consistency()
  │  ├─ Tests that derive_message_key() is deterministic
  │  └─ Asserts: Same input produces same message_key and next_chain
  │
  ├─ test_encrypt_decrypt_pair()
  │  ├─ Creates sender and receiver states with same chain key
  │  ├─ Sender encrypts "hello"
  │  ├─ Receiver decrypts
  │  └─ Asserts: Plaintext matches
  │
  └─ test_multiple_messages_ordered()
     ├─ Encrypts 3 messages in order
     ├─ Decrypts all 3
     └─ Asserts: All plaintexts correct
```

---

## DEPENDENCY GRAPH

### Top-Level Entry Flow
```
run.py
  ↓
client/main.py (typer CLI app)
  ├─ app.callback() → startup()
  │   └─ storage.token_store.load_and_set_token()
  │       └─ network.api.set_token()
  │
  ├─ register command
  │   └─ commands/register.py
  │       └─ network.auth.register_user()
  │
  ├─ login command
  │   └─ commands/login.py
  │       ├─ network.auth.login_user()
  │       ├─ network.auth.get_me()
  │       └─ storage.token_store.save_token()
  │
  ├─ init command
  │   └─ commands/init.py
  │       ├─ storage.token_store.load_and_set_token()
  │       ├─ network.auth.get_me()
  │       ├─ crypto.keys.generate_identity_keypair()
  │       ├─ crypto.keys.generate_signed_prekey()
  │       ├─ crypto.keys.generate_one_time_prekeys()
  │       ├─ storage.keystore.save_keys()
  │       └─ network.keys.upload_key_bundle()
  │
  ├─ send-cmd command
  │   └─ commands/send.py
  │       └─ services.messaging.send()
  │           ├─ storage.keystore.load_keys()
  │           ├─ storage.session_store.load_session()
  │           ├─ network.keys.fetch_key_bundle()
  │           ├─ crypto.x3dh.x3dh_sender()
  │           ├─ crypto.ratchet.init_ratchet_sender()
  │           ├─ crypto.ratchet.ratchet_encrypt()
  │           ├─ crypto.sealed_sender.seal()
  │           ├─ network.messages.api_send()
  │           └─ storage.session_store.save_session()
  │
  ├─ inbox command
  │   └─ commands/inbox.py
  │       └─ services.messaging.receive()
  │           ├─ storage.keystore.load_keys()
  │           ├─ network.messages.fetch_inbox()
  │           ├─ crypto.sealed_sender.unseal()
  │           ├─ crypto.x3dh.x3dh_receiver()
  │           ├─ crypto.ratchet.init_ratchet_receiver()
  │           ├─ crypto.ratchet.ratchet_decrypt()
  │           ├─ storage.session_store.load_session()
  │           ├─ storage.session_store.save_session()
  │           └─ network.messages.confirm_delivery()
  │
  ├─ purge command
  │   └─ commands/purge.py
  │       ├─ storage.token_store.load_and_set_token()
  │       ├─ network.messages.fetch_inbox()
  │       └─ network.messages.confirm_delivery()
  │
  └─ verify command
      └─ commands/verify.py
          └─ [STUB - not implemented]
```

### Module Dependency Tree
```
COMMANDS (7 modules)
├─ depend on: NETWORK, STORAGE, CRYPTO, SERVICES
└─ entry points: register, login, send_cmd, inbox, init, purge, verify

SERVICES (1 module)
├─ depends on: CRYPTO (X3DH, Ratchet, SealedSender)
│             NETWORK (fetch_key_bundle, send_message, fetch_inbox)
│             STORAGE (keystore, session_store)
└─ orchestrates: Full E2E encryption/decryption pipeline

CRYPTO (4 modules)
├─ keys.py: Generates X25519/Ed25519 key material
├─ x3dh.py: Initial key agreement (no dependencies on other crypto)
├─ ratchet.py: Message encryption with forward secrecy
├─ sealed_sender.py: Anonymous sender wrapping
└─ internal dependencies: Use cryptography library's primitives

NETWORK (4 modules)
├─ api.py: Base HTTP client (depends on: config, httpx)
├─ auth.py: Auth endpoints (depends on: api)
├─ keys.py: Key bundle endpoints (depends on: api)
├─ messages.py: Message endpoints (depends on: api)
└─ External dependency: httpx HTTP library

STORAGE (3 modules)
├─ keystore.py: Encrypted key files (depends on: config, cryptography)
├─ session_store.py: Encrypted session state (depends on: keystore, crypto.ratchet)
├─ token_store.py: Plain text token file (depends on: config)
└─ Internal use: 480000 iterations PBKDF2, AES-256-GCM

CONFIG (1 module)
└─ settings.py: Pydantic BaseSettings for configuration
```

---

## CRITICAL DATA FLOWS

### Message Send Flow
```
User Input: fortrx send-cmd <recipient_id> <message>
                ↓
         send_cmd() in commands/send.py
                ↓
         services.messaging.send(
           recipient_id,
           plaintext,
           storage_password,
           ttl_seconds
         )
                ↓
         [STEP 1] Load my keys
         storage.keystore.load_keys(password)
         → {"user_id", "dh_private", "dh_public", "signing_private",
            "signing_public", "signed_prekey_*", "one_time_prekeys"}
                ↓
         [STEP 2] Load/check session with recipient
         existing_session = load_session(recipient_id, password)
         
         if existing_session:
           → verify recipient's keys haven't rotated
                ↓
         [STEP 3] If new session: X3DH
         recipient_bundle = network.keys.fetch_key_bundle(recipient_id)
         → {"identity_key", "signed_prekey", "signed_prekey_signature",
            "prekey_id", "one_time_prekey"}
                ↓
         x3dh_result = crypto.x3dh.x3dh_sender(
           ik_a_private=my_identity_private,
           ik_b_public=recipient_identity_public,
           spk_b_public=recipient_signed_prekey_public,
           opk_b_public=recipient_one_time_prekey_public (optional)
         )
         → {
           "shared_secret": bytes(32),
           "ek_public": bytes(32) [ephemeral public key]
         }
                ↓
         ratchet_state = crypto.ratchet.init_ratchet_sender(
           shared_secret,
           recipient_ratchet_public
         )
         → RatchetState with initialized chains
                ↓
         [STEP 4] Encrypt message with Double Ratchet
         header, ciphertext = crypto.ratchet.ratchet_encrypt(
           ratchet_state,
           plaintext.encode()
         )
         → header = {
             "dh_public": b64(our_new_dh_public),
             "send_count": int,
             "recv_count": int,
             ...x3dh data if new session...
           }
         → ciphertext = nonce(12) + encrypted_data
                ↓
         [STEP 5] Seal with anonymous sender encryption
         sealed_bytes = crypto.sealed_sender.seal(
           sender_id=my_id,
           sender_ik_public=my_identity_public,
           recipient_ik_public=recipient_identity_public,
           ciphertext=ciphertext,
           header=header_dict
         )
         → ek_public(32) + nonce(12) + encrypted_json
                ↓
         [STEP 6] Send to server
         response = network.messages.api_send(
           recipient_id,
           sealed_blob=b64(sealed_bytes),
           message_number=ratchet_state.send_count,
           ttl_seconds
         )
         → {"id": message_id, "status": "sent", ...}
                ↓
         [STEP 7] Save updated ratchet state
         storage.session_store.save_session(
           recipient_id,
           ratchet_state,
           password
         )
         → Saves encrypted sessions.enc file
                ↓
         return response
```

### Message Receive Flow
```
User Input: fortrx inbox
                ↓
         inbox() in commands/inbox.py
                ↓
         services.messaging.receive(storage_password)
                ↓
         [STEP 1] Load my keys
         my_keys = storage.keystore.load_keys(password)
         → Extract: my_ik_private, my_spk_private, one_time_prekeys
                ↓
         [STEP 2] Fetch messages from server
         encrypted_messages = network.messages.fetch_inbox()
         → List of {
           "id": message_id,
           "sender_id": int,
           "sealed_blob": b64(sealed_bytes),
           "message_number": int,
           ...
         }
                ↓
         For each encrypted_message:
         
         [STEP 3a] Unseal to get sender info
         inner = crypto.sealed_sender.unseal(
           my_ik_private,
           sealed_blob
         )
         → {
           "sender_id": int,
           "sender_ik_public": b64(sender_identity_public),
           "ciphertext": b64(ratchet_ciphertext),
           "header": {
             "dh_public": b64(sender_new_dh_public),
             "send_count": int,
             "recv_count": int,
             ...potentially "x3dh" data...
           }
         }
                ↓
         [STEP 3b] Check if this is a new session (X3DH initialization)
         x3dh_data = inner["header"].get("x3dh")
         
         if x3dh_data:
           → NEW SESSION
           → Extract ek_public, otpk_used, otpk_public from x3dh_data
           → Look up matching one_time_prekey private if used
           
           shared_secret = crypto.x3dh.x3dh_receiver(
             ik_b_private=my_ik_private,
             spk_b_private=my_spk_private,
             ik_a_public=sender_ik_public,
             ek_a_public=ek_public,
             opk_b_private=matching_otpk_private (optional)
           )
           → bytes(32) - same as sender computed
           
           ratchet_state = crypto.ratchet.init_ratchet_receiver(
             shared_secret,
             our_ratchet_private=my_spk_private
           )
         else:
           → EXISTING SESSION
           → ratchet_state = storage.session_store.load_session(
             sender_id,
             password
           )
           → If None: log error and skip message
                ↓
         [STEP 3c] Decrypt message with Double Ratchet
         plaintext_bytes = crypto.ratchet.ratchet_decrypt(
           ratchet_state,
           header,
           ciphertext
         )
         → bytes - the original message
                ↓
         [STEP 3d] Save updated session state
         storage.session_store.save_session(
           sender_id,
           ratchet_state,
           password
         )
                ↓
         [STEP 3e] Confirm delivery (deletes from server)
         network.messages.confirm_delivery(message_id)
                ↓
         [STEP 3f] Add to results
         results.append({
           "sender_id": sender_id,
           "plaintext": plaintext_bytes.decode(),
           "message_id": message_id,
           "message_number": message_number
         })
                ↓
         return results

         Display in table:
         ├─ From | Msg # | Message | Status
         └─ Display each message with delivery status
```

---

## CRYPTOGRAPHIC ALGORITHMS SUMMARY

| Aspect | Algorithm | Implementation |
|--------|-----------|-----------------|
| **Identity Key** | X25519 (ECDH) | `cryptography.hazmat.primitives.asymmetric.x25519` |
| **Signing Key** | Ed25519 (EdDSA) | `cryptography.hazmat.primitives.asymmetric.ed25519` |
| **Initial Key Agreement** | X3DH (Signal Protocol) | Custom in `crypto/x3dh.py` |
| **Message Encryption** | Double Ratchet (Signal Protocol) | Custom in `crypto/ratchet.py` |
| **Anonymous Sender** | Sealed Sender (Signal Protocol) | Custom in `crypto/sealed_sender.py` |
| **Key Derivation** | HKDF-SHA256 | `cryptography.hazmat.primitives.kdf.hkdf` |
| **Chain Keys** | HMAC-SHA256 | Python `hmac` module |
| **Message Encryption** | AES-256-GCM | `cryptography.hazmat.primitives.ciphers.aead.AESGCM` |
| **Password Derivation** | PBKDF2-HMAC-SHA256 (480k iter) | `cryptography.hazmat.primitives.kdf.pbkdf2` |
| **Encoding** | Base64 | Python `base64` module |

---

## FILE STRUCTURE SUMMARY

```
c:\Users\himan\Documents\GitHub\Fortrx-Client\
├── README.md (project description)
├── requirements.txt (dependencies)
├── run.py (entry point)
├── CODEBASE_MAP.md (this file)
│
├── client/
│   ├── __init__.py
│   ├── config.py (Settings class)
│   ├── main.py (CLI app root)
│   │
│   ├── commands/ (7 CLI commands)
│   │   ├── __init__.py
│   │   ├── register.py
│   │   ├── login.py
│   │   ├── send.py
│   │   ├── inbox.py
│   │   ├── init.py
│   │   ├── verify.py (stub)
│   │   └── purge.py
│   │
│   ├── network/ (HTTP API client)
│   │   ├── __init__.py
│   │   ├── api.py (base HTTP + FortrxAPIError)
│   │   ├── auth.py (login, register, get_me)
│   │   ├── keys.py (key bundle upload/fetch)
│   │   ├── messages.py (send, fetch, confirm)
│   │   └── ws.py (empty - websocket planned)
│   │
│   ├── crypto/ (E2E encryption)
│   │   ├── __init__.py
│   │   ├── keys.py (key generation)
│   │   ├── x3dh.py (initial key agreement)
│   │   ├── ratchet.py (message encryption)
│   │   └── sealed_sender.py (anonymous sender)
│   │
│   ├── services/ (high-level orchestration)
│   │   ├── __init__.py
│   │   └── messaging.py (send/receive pipeline)
│   │
│   └── storage/ (persistent data)
│       ├── __init__.py
│       ├── keystore.py (encrypted keys file)
│       ├── session_store.py (encrypted session state)
│       └── token_store.py (JWT token file)
│
└── tests/
    ├── test_encoding.py (session and sealed_sender tests)
    └── test_ratchet.py (ratchet crypto tests)
```

---

## CONFIGURATION & ENVIRONMENT

### Storage Locations
```
.fortrx/
├── token                    # Plain text JWT token (not encrypted)
├── keys.enc                 # Legacy encrypted keys file
├── keys_{user_id}.enc       # Per-user encrypted keys (preferred)
└── sessions.enc             # Encrypted session state (all conversations)
```

### Dependencies
```
httpx                      # HTTP client
websockets                 # WebSocket (infrastructure, not yet used)
cryptography              # Cryptographic primitives
python-dotenv             # Environment variable loading
pydantic                  # Data validation
typer                     # CLI framework
rich                      # Terminal formatting
anyio                     # Async I/O utilities
pydantic-settings         # Pydantic settings management
passlib                   # Password utilities (listed but not used in client)
```

### Server Endpoints
```
BASE_URL: http://localhost:8000

Auth:
  POST   /auth/register           - Register new user
  POST   /auth/login              - Login (returns JWT)
  GET    /auth/me                 - Get current user info

Keys:
  POST   /keys/upload             - Upload key bundle
  GET    /keys/{user_id}          - Fetch user's public keys

Messages:
  POST   /messages/send           - Send encrypted message
  GET    /messages/inbox          - Fetch received messages
  GET    /messages/conversation/{user_id} - Fetch conversation history
  DELETE /messages/{message_id}/confirm  - Confirm delivery (purge)
```

---

## SECURITY NOTES

⚠️ **Security Considerations:**
1. **Token Storage**: JWT tokens stored in plain text at `.fortrx/token`
2. **Key Storage**: Keys encrypted with PBKDF2-HMAC-SHA256 (480k iterations) + AES-256-GCM
3. **Session Storage**: Sessions encrypted with same method as keys
4. **Forward Secrecy**: Double Ratchet provides forward secrecy (old message keys cannot decrypt new ones)
5. **Identity Verification**: No built-in identity verification (fingerprint verification would be manual)
6. **X3DH Anti-Replay**: Optional one-time prekeys provide anti-replay protection for first message

---

## USAGE EXAMPLES

```bash
# 1. Register
python run.py register alice alice@example.com
(prompts for password)

# 2. Login
python run.py login alice
(prompts for password)

# 3. Initialize keys
python run.py init
(prompts for storage password)

# 4. Send message
python run.py send-cmd 2 "Hello Bob"
(prompts for storage password)

# 5. Receive messages
python run.py inbox
(prompts for storage password)

# 6. Purge all messages
python run.py purge

# 7. With explicit options
python run.py send-cmd 2 "Hi" --ttl 3600 --password mypass
python run.py inbox --password mypass
```

---

## NEXT STEPS / TODOs

- [ ] Implement `verify()` command for identity verification
- [ ] Implement WebSocket support (`client/network/ws.py`)
- [ ] Add fingerprint/key verification UI
- [ ] Implement group messaging
- [ ] Add media/file attachment support
- [ ] Implement message reactions/editing
- [ ] Add offline message queue
- [ ] Implement push notifications

---

*Generated: April 5, 2026*
*Project: Fortrx-Client (Encrypted Messaging)*
*Status: Core E2E encryption fully functional*
