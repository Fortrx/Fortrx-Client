# FORTRX COMPLETE ECOSYSTEM MAP - ALL COMPONENTS

**Complete Scope**: Fortress Server + Fortrx-Client  
**Language**: Python 3.9+  
**Protocol**: Signal Protocol (X3DH + Double Ratchet)  
**Components**: 2 servers + 1 CLI client  
**Generated**: April 5, 2026

---

## 📍 QUICK NAVIGATION

- [PART 1: FORTRESS SERVER](#part-1-fortress-server)
- [PART 2: FORTRX CLIENT](#part-2-fortrx-client)
- [PART 3: INTEGRATION FLOWS](#part-3-integration-flows)
- [PART 4: DATABASE SCHEMA](#part-4-database-schema)
- [PART 5: API ROUTES COMPLETE](#part-5-api-routes-complete)
- [PART 6: DEPENDENCY TREE](#part-6-dependency-tree)
- [PART 7: ALL FUNCTIONS REFERENCE](#part-7-all-functions-reference)

---

# PART 1: FORTRESS SERVER

**Location**: `c:\Users\himan\Documents\GitHub\Fortress\`  
**Entry**: `run.py` → `app/main.py`  
**Framework**: FastAPI + Uvicorn  
**Database**: SQLAlchemy ORM (PostgreSQL/SQLite)  
**Storage**: S3/MinIO/LocalStack (blob storage)  
**Cache**: Redis (pub/sub, sessions)

## 1.1 Server Entry Point

### `run.py`
```python
import uvicorn

# Starts FastAPI server on 127.0.0.2:8000 with hot reload
uvicorn.run(
    "app.main:app",
    host='127.0.0.2',
    port=8000,
    reload=True
)
```

## 1.2 Main Application - `app/main.py`

```python
FastAPI Application Root

Lifespan: async context manager
├─ Startup:
│  ├─ Create database tables → Base.metadata.create_all(bind=engine)
│  ├─ Ensure S3 bucket exists → ensure_bucket_exists()
│  └─ Start background cleanup task → expired_message_cleanup()
│
├─ Cleanup (shutdown):
│  └─ Cancel background task

Background Worker: expired_message_cleanup()
├─ Runs every 60 seconds
├─ Calls: purge_expired_messages(db)
┼ Returns: count of deleted messages
└─ On error: Logs and continues

Registered Routers (5 total):
├─ keys.router         → /keys endpoints
├─ auth.router         → /auth endpoints
├─ messages.router     → /messages endpoints
├─ ws.router           → /ws (WebSocket)
└─ safety.router       → Safety features

Exception Handlers:
└─ RateLimitExceeded → HTTP 429

Middleware:
└─ SecurityHeadersMiddleware

Health Endpoint: GET /
└─ Returns: {"status": "Fortrx is running"}
```

## 1.3 Configuration - `app/config.py`

```python
Class: Settings(BaseSettings)

Attributes:
├─ SECRET_KEY: str
│  └─ JWT signing key
├─ DATABASE_URL: str
│  └─ SQLAlchemy connection string
├─ ALGORITHM: str = "HS256"
│  └─ JWT algorithm
├─ ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
│  └─ JWT expiration time
├─ S3_PROVIDER: str = "minio" (aws|minio|localstack)
├─ S3_ENDPOINT_URL: str | None
├─ S3_ACCESS_KEY: str
├─ S3_SECRET_KEY: str
├─ S3_BUCKET_NAME: str
├─ S3_REGION: str = "us-east-1"
├─ REDIS_URL: str
│  └─ Redis connection string
└─ RATE_LIMIT_STORAGE: str = "memory://"
   └─ Rate limit backend (memory, redis, etc.)

Loads from: .env file

Singleton Instance:
└─ settings = Settings()
```

## 1.4 Database - `app/database.py`

```python
SQLAlchemy Configuration

Variables:
├─ DATABASE_URL: str (from settings)
├─ sync_database_url: str
│  └─ Converts async PostgreSQL URL to sync
├─ engine: Engine
│  └─ SQLAlchemy engine with echo=True
└─ SessionLocal: sessionmaker
   └─ Session factory

Base: declarative_base()
└─ ORM base class for all models

Functions:
└─ get_db() → Generator[Session]
   ├─ Creates session
   ├─ Yields for dependency injection
   └─ Closes on exit
```

## 1.5 Models - `app/models/`

### User Model (`user.py`)
```python
Table: users

Columns:
├─ id: Integer (PK, autoincrement)
├─ username: String (UNIQUE, NOT NULL)
├─ email: String (UNIQUE, NOT NULL)
├─ hashed_password: String (NOT NULL)
├─ identity_public_key: String (nullable)
│  └─ Cached identity key from latest key bundle
├─ created_at: DateTime (default: now)
└─ is_active: Boolean (default: True)
```

### Message Model (`message.py`)
```python
Table: messages

Columns:
├─ id: Integer (PK)
├─ recipient_id: Integer (NOT NULL)
│  └─ FK to user receiving message
├─ sender_id: Integer (implied from path logic)
├─ sealed_blob: String (NOT NULL)
│  └─ S3 blob key (data stored in object storage)
├─ message_number: Integer
│  └─ Double ratchet counter
├─ created_at: DateTime (default: now)
└─ expires_at: DateTime (nullable)
   └─ TTL for automatic deletion
```

### KeyBundle Model (`key_bundle.py`)
```python
Table: key_bundles

Columns:
├─ id: Integer (PK)
├─ user_id: Integer (NOT NULL, indexed)
│  └─ FK to user
├─ identity_key: Text
│  └─ X25519 public key (base64)
├─ signed_prekey: Text
│  └─ X25519 public key (base64)
├─ signed_prekey_signature: Text
│  └─ Ed25519 signature of signed_prekey
├─ prekey_id: Integer
│  └─ Prekey rotation counter
├─ one_time_prekeys: Text
│  └─ JSON array of base64-encoded keys
└─ updated_at: DateTime (default: now)
```

## 1.6 Routers - `app/routers/`

### Authentication Router (`auth.py`)

```
Endpoint: POST /auth/register
├─ Rate limit: 5/minute
├─ Request: UserCreate { username, email, password }
├─ Response: UserResponse { id, username, email, is_active, created_at }
├─ Call: services.auth_service.register_user(db, username, email, password)
└─ Errors:
   ├─ 400: Username/email already exists
   └─ 422: Invalid payload

Endpoint: POST /auth/login
├─ Rate limit: 10/minute
├─ Request: OAuth2PasswordRequestForm { username, password }
├─ Response: TokenResponse { access_token, token_type }
├─ Call: services.auth_service.login_user(db, username, password)
└─ Returns: JWT token for future API calls

Endpoint: GET /auth/me
├─ Auth: Required (Bearer token)
├─ Response: UserResponse { id, username, email, is_active, created_at }
├─ Call: get_active_user(token)
└─ Returns: Current authenticated user
```

### Keys Router (`keys.py`)

```
Endpoint: POST /keys/upload
├─ Auth: Required (Bearer token)
├─ Request: KeyBundleUpload {
│  ├─ identity_key: str (b64)
│  ├─ signed_prekey: str (b64)
│  ├─ signed_prekey_signature: str (b64)
│  ├─ prekey_id: int
│  └─ one_time_prekeys: list[str] (b64)
│ }
├─ Response: {"message": "Key bundle uploaded successfully"}
├─ Call: services.key_service.upload_key_bundle(db, user_id, payload)
├─ Side effect: Creates or updates KeyBundle in DB
└─ Status: 201 Created

Endpoint: GET /keys/{user_id}
├─ Auth: Required (Bearer token)
├─ Response: KeyBundleResponse {
│  ├─ user_id: int
│  ├─ identity_key: str (b64)
│  ├─ signed_prekey: str (b64)
│  ├─ signed_prekey_signature: str (b64)
│  ├─ prekey_id: int
│  └─ one_time_prekey: str (b64) | None
│ }
├─ Call: services.key_service.fetch_key_bundle(db, user_id)
├─ Side effect: Pops one OTP key from bundle (consumes it)
└─ Status: 200 OK
```

### Messages Router (`messages.py`)

```
Endpoint: POST /messages/send
├─ Auth: Required (Bearer token)
├─ Request: MessageSend {
│  ├─ recipient_id: int
│  ├─ sealed_blob: str (b64 - encoded ciphertext)
│  ├─ message_number: int
│  └─ ttl_seconds: int | None
│ }
├─ Response: MessageResponse { id, recipient_id, message_number, sealed_blob, created_at, expires_at }
├─ Call: await services.message_service.send_message(db, sender_id, payload)
├─ Side effects:
│  ├─ Upload blob to S3
│  ├─ Create message record in DB
│  └─ Notify recipient via WebSocket (if connected)
└─ Status: 201 Created

Endpoint: GET /messages/inbox
├─ Auth: Required (Bearer token)
├─ Response: list[MessageResponse]
│  └─ All messages for current user
├─ Call: services.message_service.fetch_inbox(db, current_user.id)
├─ Side effect: Download blobs from S3, encode to base64
└─ Status: 200 OK

Endpoint: DELETE /messages/{message_id}/confirm
├─ Auth: Required (Bearer token)
├─ Request: message_id (path parameter)
├─ Response: {"message": "deleted"}
├─ Call: services.message_service.confirm_delivery(db, message_id, user_id)
├─ Side effects:
│  ├─ Delete blob from S3
│  ├─ Delete message record from DB
│  └─ Verify ownership (user_id == message.recipient_id)
└─ Status: 200 OK
```

### WebSocket Router (`ws.py`)

```
Endpoint: WebSocket /ws/{user_id}
├─ Auth: Required (token in query param)
├─ Connection flow:
│  ├─ Decode token
│  ├─ Verify token.sub == user_id
│  ├─ Accept connection
│  ├─ Subscribe to Redis channel
│  └─ Listen for messages
│
├─ Listeners:
│  ├─ redis_listener(): Monitor Redis pub/sub
│  ├─ ws_listener(): Monitor client messages (ping)
│  └─ Concurrent via asyncio.wait()
│
└─ On disconnect:
   ├─ Unsubscribe from Redis
   └─ Clean up connections
```

### Safety Router (`safety.py`)
```
Status: Placeholder for security features
```

## 1.7 Services - `app/services/`

### Auth Service (`auth_service.py`)

```python
Function: register_user(db, username, email, password) → UserResponse

Flow:
├─ Check username unique:
│  └─ get_user_by_username(db, username)
│  └─ If exists: HTTPException 400 "Username already exists"
│
├─ Check email unique:
│  └─ get_user_by_email(db, email)
│  └─ If exists: HTTPException 400 "Email already exists"
│
├─ Hash password:
│  └─ hash_password(password)
│
└─ Create user:
   └─ repositories.user_repo.create_user(db, username, email, hashed_password)

Function: login_user(db, username, password) → str (token)

Flow:
├─ Look up user:
│  └─ get_user_by_username(db, username)
│  └─ If None: HTTPException 401 "Invalid Credentials"
│
├─ Verify password:
│  └─ verify_password(password, user.hashed_password)
│  └─ If False: HTTPException 401 "Invalid Credentials"
│
└─ Create token:
   └─ create_token_for_user(user.id, user.username)
   └─ Returns: JWT token string
```

### Key Service (`key_service.py`)

```python
Function: upload_key_bundle(db, user_id, payload: KeyBundleUpload) → KeyBundle

Flow:
├─ Serialize OTP keys to JSON string
│  └─ because SQLite Text column can't store Python list
│
├─ Check if bundle already exists:
│  └─ get_bundle_by_user_id(db, user_id)
│
├─ If exists:
│  └─ Update bundle with new keys
│
└─ If not:
   └─ Create new bundle
   └─ Update user.identity_public_key (for caching)

Function: fetch_key_bundle(db, user_id) → KeyBundleResponse

Flow:
├─ Fetch bundle:
│  └─ get_bundle_by_user_id(db, user_id)
│  └─ If None: HTTPException 404 "Key Bundle not found"
│
├─ Deserialize OTP keys from JSON
│
├─ Pop first OTP key:
│  └─ Consumes one-time prekey (anti-replay)
│  └─ Saves back to DB
│
└─ Return response with popped OTP key
```

### Message Service (`message_service.py`)

```python
Async Function: send_message(db, sender_id, payload: MessageSend) → Message

Flow:
├─ Verify recipient exists:
│  └─ get_user_by_id(db, payload.recipient_id)
│  └─ If None: HTTPException 404 "Recipient not found"
│
├─ Generate S3 blob key:
│  └─ generate_blob_key(recipient_id)
│
├─ Upload sealed blob to S3:
│  ├─ Decode base64 payload.sealed_blob
│  └─ upload_blob(blob_key, raw_bytes)
│
├─ Calculate expiration if TTL provided:
│  └─ expires_at = now + timedelta(seconds=ttl_seconds)
│
├─ Save message record to DB:
│  └─ message_repo.save_message(
│     recipient_id,
│     message_number,
│     sealed_blob=blob_key,  (points to S3)
│     expires_at
│  )
│
├─ Notify recipient via WebSocket:
│  └─ manager.send_to_user(recipient_id, {
│     "type": "new_message",
│     "message_id": id,
│     "message_number": number,
│     "expires_at": iso_string
│  })
│
└─ Return message object

Function: fetch_inbox(db, user_id) → list[Message]

Flow:
├─ Query all messages for user:
│  └─ message_repo.get_message_for_user(db, user_id)
│
├─ For each message:
│  ├─ Download blob from S3:
│  │  └─ download_blob(message.sealed_blob)
│  │
│  └─ Encode to base64:
│     └─ msg.sealed_blob = b64encode(raw).decode()
│
└─ Return modified messages (sealed_blob now contains b64 data instead of key)

Function: confirm_delivery(db, message_id, user_id) → dict

Flow:
├─ Fetch message:
│  └─ Query Message by ID
│  └─ If None: HTTPException 403 "Message not found"
│
├─ Verify ownership:
│  └─ If message.recipient_id != user_id: HTTPException 403 "Not allowed"
│
├─ Delete blob from S3:
│  └─ delete_blob(message.sealed_blob)
│  └─ Catch exception (best-effort)
│
├─ Delete message record:
│  └─ message_repo.delete_message(db, message_id)
│
└─ Return {"message": "deleted"}

Function: purge_expired_messages(db) → int(count)

Flow:
├─ Query all expired messages:
│  └─ message_repo.get_expired_messages(db)
│  └─ WHERE expires_at != NULL AND expires_at < now
│
├─ For each expired message:
│  ├─ Delete blob from S3 (best-effort)
│  └─ Delete message record
│
└─ Return count of deleted messages
```

### Storage Service (`storage_service.py`)

```python
S3/MinIO Client Functions

Function: get_s3_client() → boto3.client('s3')
├─ Connects to S3 provider
├─ Uses settings: S3_ENDPOINT_URL, access_key, secret_key
└─ Returns connected boto3 client

Function: ensure_bucket_exists() → None
├─ Get S3 client
├─ Try to create bucket with settings.S3_BUCKET_NAME
├─ Catch exception if already exists
└─ Idempotent

Function: generate_blob_key(recipient_id: int) → str
├─ Format: f"messages/{user_id}/{timestamp}_{random}.enc"
└─ Unique per message, namespaced by recipient

Function: upload_blob(blob_key: str, raw_bytes: bytes) → None
├─ Get S3 client
└─ s3_client.put_object(Bucket=..., Key=blob_key, Body=raw_bytes)

Function: download_blob(blob_key: str) → bytes
├─ Get S3 client
└─ s3_client.get_object(Bucket=..., Key=blob_key)['Body'].read()

Function: delete_blob(blob_key: str) → None
├─ Get S3 client
└─ s3_client.delete_object(Bucket=..., Key=blob_key)
```

### Connection Manager (`connection_manager.py`)

```python
Class: ConnectionManager

Attributes:
└─ active_connections: dict[int, WebSocket]
   ├─ Key: user_id
   └─ Value: WebSocket connection

Methods:
├─ async connect(user_id: int, websocket: WebSocket) → None
│  ├─ Accept WebSocket
│  └─ Store in active_connections
│
├─ disconnect(user_id: int) → None
│  └─ Remove from active_connections
│
├─ async send_to_user(user_id: int, data: dict) → None
│  └─ Publish message to Redis channel (pubsub system)
│
└─ is_online(user_id: int) → bool
   └─ Check if user_id in active_connections

Singleton Instance:
└─ manager = ConnectionManager()
```

### Pub/Sub Service (`pubsub.py`)

```python
Redis Pub/Sub Functions

Function: get_redis() → redis.asyncio.Redis
├─ Connects to REDIS_URL from settings
└─ Returns async Redis client

Async Function: publish_message(user_id: int, message: dict) → None
├─ Get Redis client
├─ Channel name: f"user:{user_id}"
└─ redis.publish(channel, json.dumps(message))

Async Function: subscribe_to_user(user_id: int) → tuple(pubsub, redis_client)
├─ Get Redis client
├─ Create pubsub listener
├─ Subscribe to f"user:{user_id}"
└─ Returns connection for listening

Async Function: unsubscribe_from_user(pubsub, redis_client) → None
├─ Unsubscribe from channel
└─ Close connections
```

## 1.8 Repositories - `app/repositories/`

### User Repository (`user_repo.py`)

```python
Function: get_user_by_id(db, id: int) → User | None
├─ Query User WHERE id = id
└─ Returns first result or None

Function: get_user_by_username(db, username: str) → User | None
├─ Query User WHERE username = username
└─ Returns first result or None

Function: get_user_by_email(db, email: str) → User | None
├─ Query User WHERE email = email
└─ Returns first result or None

Function: create_user(db, username, email, hashed_password) → User
├─ Create User instance
├─ Add to session
├─ Commit and refresh
└─ Returns created User object
```

### Message Repository (`message_repo.py`)

```python
Function: save_message(db, recipient_id, message_number, sealed_blob, expires_at=None) → Message
├─ Create Message instance
├─ Add to session
├─ Commit and refresh
└─ Returns Message object

Function: get_message_for_user(db, user_id: int) → list[Message]
├─ Query WHERE recipient_id = user_id
├─ Order by created_at ASC
└─ Returns all messages for user

Function: delete_message(db, message_id: int) → Message | None
├─ Query Message by ID
├─ If found: delete and commit
└─ Returns deleted Message or None

Function: get_expired_messages(db) → list[Message]
├─ Query WHERE expires_at != NULL AND expires_at < now
└─ Returns all expired messages
```

### Key Repository (`key_repo.py`)

```python
Function: get_bundle_by_user_id(db, user_id: int) → KeyBundle | None
├─ Query WHERE user_id = user_id
└─ Returns first result or None

Function: create_bundle(db, user_id, identity_key, signed_prekey, signed_prekey_signature, prekey_id, one_time_prekeys: list) → KeyBundle
├─ Serialize OTP list to JSON
├─ Create KeyBundle instance
├─ Add to session
├─ Commit and refresh
└─ Returns KeyBundle object

Function: update_bundle(db, bundle: KeyBundle, **fields) → KeyBundle
├─ For each field:
│  ├─ If field is one_time_prekeys and is list: JSON dump
│  └─ setattr(bundle, field, value)
├─ Commit and refresh
└─ Returns updated bundle

Function: pop_one_time_prekey(db, bundle: KeyBundle) → str | None
├─ Parse one_time_prekeys JSON
├─ Pop last key from list
├─ Serialize back to JSON
├─ Commit
└─ Returns popped key or None
```

## 1.9 Schemas - `app/schemas/`

### User Schemas (`user.py`)

```python
Class: UserCreate(BaseModel)
├─ username: str
├─ email: str
└─ password: str

Class: UserLogin(BaseModel)
├─ username: str
└─ password: str

Class: UserResponse(BaseModel)
├─ id: int
├─ username: str
├─ email: str
├─ is_active: bool
└─ created_at: datetime
   └─ Config: from_attributes = True

Class: TokenResponse(BaseModel)
├─ access_token: str
└─ token_type: str = "bearer"
```

### Message Schemas (`message.py`)

```python
Class: MessageSend(BaseModel)
├─ recipient_id: int
├─ sealed_blob: str (base64 encoded)
├─ message_number: int
└─ ttl_seconds: int | None = None

Class: MessageResponse(BaseModel)
├─ id: int
├─ recipient_id: int
├─ message_number: int
├─ sealed_blob: str (base64 in response)
├─ created_at: datetime
└─ expires_at: datetime | None
   └─ Config: from_attributes = True
```

### Key Bundle Schemas (`key_bundle.py`)

```python
Class: KeyBundleUpload(BaseModel)
├─ identity_key: str (base64)
├─ signed_prekey: str (base64)
├─ signed_prekey_signature: str (base64)
├─ prekey_id: int
└─ one_time_prekeys: list[str] (base64)

Class: KeyBundleResponse(BaseModel)
├─ user_id: int
├─ identity_key: str (base64)
├─ signed_prekey: str (base64)
├─ signed_prekey_signature: str (base64)
├─ prekey_id: int
└─ one_time_prekey: str (base64) | None
   └─ Config: from_attributes = True
```

## 1.10 Cryptography - `app/crypto/`

### Hashing (`hashing.py`)

```python
pwd_context = CryptContext(schemes=['bcrypt_sha256', 'bcrypt'], deprecated='auto')

Function: hash_password(plain_password: str) → str
├─ Uses bcrypt hashing
└─ Returns hashed password

Function: verify_password(plain_password: str, hashed_password: str) → bool
├─ Compares plain with hashed using bcrypt
└─ Returns True if match
```

### Tokens (`tokens.py`)

```python
Function: create_access_token(data: dict) → str
├─ Copy data
├─ Add exp = now + ACCESS_TOKEN_EXPIRE_MINUTES
├─ Encode with SECRET_KEY using HS256
└─ Returns JWT token

Function: decode_access_token(token: str) → dict | None
├─ Try: jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
├─ Except JWTError: return None
└─ Returns payload dict or None

Function: create_token_for_user(user_id: int, username: str) → str
├─ Create access token with data:
│  ├─ sub: str(user_id)
│  └─ username: username
└─ Returns JWT token
```

### Keys (`keys.py`)

```python
Mirrors client crypto/keys.py (see FORTRX-CLIENT section below)
- generate_identity_keypair()
- generate_signed_prekey()
- generate_one_time_prekeys()
- encode_public_key()
- decode_public_key()
```

### X3DH (`x3dh.py`)

```python
Mirrors client crypto/x3dh.py (see FORTRX-CLIENT section below)
- x3dh_sender()
- x3dh_receiver()
```

### Ratchet (`ratchet.py`)

```python
Mirrors client crypto/ratchet.py (see FORTRX-CLIENT section below)
- RatchetState class
- init_ratchet_sender()
- init_ratchet_receiver()
- ratchet_encrypt()
- ratchet_decrypt()

SERVER NOTE: Server stores encrypted ratchet state belongs to client,
not used on server-side message processing
```

### Sealed Sender (`sealed_sender.py`)

```python
Mirrors client crypto/sealed_sender.py (see below)
- seal()
- unseal()
```

### Fingerprint (`fingerprint.py`)

```
Status: Placeholder for identity verification features
```

## 1.11 Dependencies - `app/dependencies/`

### Auth Dependencies (`auth.py`)

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

Function: get_current_user(token: str, db: Session) → User
├─ token = Depends(oauth2_scheme)
├─ Decode token → decode_access_token(token)
├─ If None: HTTPException 401 "Invalid or expired token"
├─ Get user_id from payload["sub"]
├─ Query User by id
├─ If None: HTTPException 401 "User not found"
└─ Returns User object

Function: get_active_user(current_user: User) → User
├─ current_user = Depends(get_current_user)
├─ If not current_user.is_active:
│  └─ HTTPException 403 "Account Disabled"
└─ Returns User object
```

## 1.12 Middleware - `app/middleware/`

### Rate Limiting (`rate_limit.py`)

```python
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.RATE_LIMIT_STORAGE
)

Usage: @limiter.limit("5/minute") on endpoints
```

### Security Headers (`security_headers.py`)

```python
Class: SecurityHeadersMiddleware(BaseHTTPMiddleware)
├─ Adds security headers to responses
│  ├─ X-Content-Type-Options: nosniff
│  ├─ X-Frame-Options: DENY
│  ├─ X-XSS-Protection: 1; mode=block
│  └─ Strict-Transport-Security
│
└─ Processes all responses
```

---

# PART 2: FORTRX CLIENT

**Location**: `c:\Users\himan\Documents\GitHub\Fortrx-Client\`  
**Entry**: `run.py` → `client/main.py`  
**Framework**: Typer (CLI) + Cryptography  
**Storage**: Encrypted files (.fortrx/)

## 2.1 Client Entry Point

### `run.py`
```python
from client.main import app

if __name__ == "__main__":
    app()
```

## 2.2 Main Application - `client/main.py`

```python
Typer CLI Application

app = typer.Typer(name="fortrx", help="Encrypted Messaging Client")

Registered Commands (7):
├─ register.register()     → fortrx register <username> <email>
├─ login.login()           → fortrx login <username>
├─ send.send_cmd()         → fortrx send-cmd <recipient_id> <message>
├─ inbox.inbox()           → fortrx inbox
├─ verify.verify()         → fortrx verify <user_id>
├─ init.init()             → fortrx init
└─ purge.purge()           → fortrx purge

Startup Callback:
├─ On every command: load_and_set_token()
└─ Initializes global token for API calls
```

## 2.3 Configuration - `client/config.py`

```python
Class: Settings(BaseSettings)

Attributes:
├─ SERVER_URL: str = "http://localhost:8000"
├─ LOCAL_STORAGE_PATH: str = ".fortrx"
├─ TOKEN_FILE: str = ".fortrx/token"
├─ KEYS_FILE: str = ".fortrx/keys.enc"
├─ SESSION_FILE: str = ".fortrx/sessions.enc"
├─ STORAGE_PASSWORD: str = ""

Singleton: settings = Settings()
```

## 2.4 Commands - `client/commands/`

### Register Command (`register.py`)

```python
Function: register(
    username: str (Argument),
    email: str (Argument),
    password: str (Option, hidden)
) → None

Flow:
├─ Call: network.auth.register_user(username, email, password)
│  └─ POST /auth/register
│
├─ On success:
│  ├─ Print: "✅ Registered! Welcome, {username}"
│  └─ Print: "Your User ID: {user_id}"
│
└─ On error (FortrxAPIError):
   ├─ Print error message
   └─ Exit(1)
```

### Login Command (`login.py`)

```python
Function: login(
    username: str (Argument),
    password: str (Option, hidden)
) → None

Flow:
├─ Call: network.auth.login_user(username, password)
│  └─ POST /auth/login → returns JWT token
│
├─ Call: network.auth.get_me()
│  └─ GET /auth/me → get user info
│
├─ Call: storage.token_store.save_token(token)
│  └─ Save token to .fortrx/token
│
├─ On success:
│  ├─ Print: "✅ Logged in! Hello, {username}"
│  ├─ Print: "User ID: {user_id}"
│  └─ Print: "Session saved locally"
│
└─ On error: Print error and exit(1)
```

### Send Command (`send.py`)

```python
Function: send_cmd(
    recipient_id: int (Argument),
    message: str (Argument),
    ttl: int (Option, --ttl),
    password: str (Option, --password, -p)
) → None

Flow:
├─ Load and set token
│  └─ load_and_set_token()
│
├─ Prompt for storage password if not provided
│
├─ Call: services.messaging.send(
│    recipient_id,
│    plaintext=message,
│    storage_password=password,
│    ttl_seconds=ttl
│  )
│  └─ Full E2E encryption pipeline (see below)
│
├─ On success:
│  ├─ Print: "✔️ Message sent"
│  ├─ Print: "Message ID: {id}"
│  └─ Print: "Expires in: {ttl}s" (if TTL set)
│
└─ On error: Print error and exit(1)
```

### Inbox Command (`inbox.py`)

```python
Function: inbox(
    password: str (Option, --password, -p)
) → None

Flow:
├─ Load and set token
├─ Prompt for storage password if not provided
├─ Call: services.messaging.receive(storage_password)
│  └─ Full E2E decryption pipeline (see below)
├─ If no messages: Print "No new messages."
├─ Else: Display table with:
│  ├─ From (sender_id)
│  ├─ Msg # (message_number)
│  ├─ Message (plaintext)
│  └─ Status (✔️ delivered or ❌ error)
└─ Print: "{count} message(s) processed"
```

### Init Command (`init.py`)

```python
Function: init(
    force: bool (Option, --force),
    password: str (Option, --password, -p)
) → None

Flow:
├─ Check logged in: load_and_set_token()
│  └─ If No: Print error and exit(1)
│
├─ Check keys don't exist:
│  └─ keys_exist()
│  └─ If exist and not --force: Print warning and exit(1)
│
├─ Prompt for storage password (if not provided)
│  └─ Confirmation prompt (type twice)
│
├─ Get current user: network.auth.get_me()
│  └─ Get user_id
│
├─ Generate keys (with progress indicator):
│  ├─ Identity keypair: crypto.keys.generate_identity_keypair()
│  │  ├─ X25519 DH keypair
│  │  └─ Ed25519 signing keypair
│  │
│  ├─ Signed prekey: crypto.keys.generate_signed_prekey(signing_private)
│  │  ├─ X25519 prekey
│  │  └─ Ed25519 signature
│  │
│  └─ One-time prekeys: crypto.keys.generate_one_time_prekeys(10)
│     └─ 10x X25519 keypairs
│
├─ Prepare keys_dict for storage:
│  ├─ user_id
│  ├─ All keys base64 encoded
│  ├─ Serialized one_time_prekeys
│  └─ prekey_id: 1
│
├─ Save locally: storage.keystore.save_keys(keys_dict, password)
│  └─ Saves to .fortrx/keys_{user_id}.enc (encrypted)
│
├─ Upload to server: network.keys.upload_key_bundle(
│    identity_key,
│    signed_prekey,
│    signed_prekey_signature,
│    prekey_id,
│    one_time_prekeys
│  )
│
└─ On success:
   ├─ Print key hashes (first 20 chars)
   ├─ Print "10 one-time prekeys uploaded"
   ├─ Print file location
   └─ Print "Private keys never left this device"
```

### Verify Command (`verify.py`)

```python
Function: verify(user_id: int) → None
├─ Status: STUB (not implemented)
└─ Prints: "verify command — wired in C19"
```

### Purge Command (`purge.py`)

```python
Function: purge() → None

Flow:
├─ Load and set token
├─ Fetch all messages: network.messages.fetch_inbox()
│  └─ GET /messages/inbox
│
├─ If no messages: Print "No messages to purge."
│
├─ For each message:
│  ├─ Confirm delivery: network.messages.confirm_delivery(msg_id)
│  │  └─ DELETE /messages/{msg_id}/confirm
│  │
│  └─ Increment count
│
└─ Print: "Purged {count} message(s)."
```

## 2.5 Network - `client/network/`

### Base API Client (`api.py`)

```python
Global State:
└─ _token: str | None

Function: set_token(token: str) → None
└─ Sets global _token

Function: get_token() → str | None
└─ Returns global _token

Function: _headers() → dict
├─ If _token: {"Authorization": "Bearer {_token}"}
└─ Else: {}

Function: get(endpoint: str, **kwargs) → httpx.Response
├─ url = settings.SERVER_URL + endpoint
└─ httpx.get(url, headers=_headers(), **kwargs)

Function: post(endpoint: str, json: dict, data: dict, **kwargs) → httpx.Response
├─ url = settings.SERVER_URL + endpoint
└─ httpx.post(url, json, data, headers, **kwargs)

Function: delete(endpoint: str, **kwargs) → httpx.Response
├─ url = settings.SERVER_URL + endpoint
└─ httpx.delete(url, headers=_headers(), **kwargs)

Function: raise_for_status(response: httpx.Response, context: str) → None | Raises
├─ If status_code >= 400:
│  ├─ Extract detail from response.json() or response.text
│  └─ Raise FortrxAPIError
│
└─ Else: Continue

Exception: FortrxAPIError(Exception)
├─ Attributes: status_code, detail, context
└─ Message: "[{status_code}]{context}:{detail}"
```

### Auth Endpoints (`auth.py`)

```python
Function: register(username: str, email: str, password: str) → dict
├─ POST /auth/register
├─ Payload: {"username", "email", "password"}
└─ Returns: {"id", "username", "email", ...}

Function: login(username: str, password: str) → str
├─ POST /auth/login (form-encoded)
├─ Calls: set_token(token)
└─ Returns: JWT token string

Function: get_me() → dict
├─ GET /auth/me
└─ Returns: {"id", "username", "email", ...}
```

### Keys Endpoints (`keys.py`)

```python
Function: upload_key_bundle(
    identity_key: str (b64),
    signed_prekey: str (b64),
    signed_prekey_signature: str (b64),
    prekey_id: int,
    one_time_prekeys: list[str] (b64)
) → dict
├─ POST /keys/upload
└─ Returns: {"message", ...}

Function: fetch_key_bundle(user_id: int) → dict
├─ GET /keys/{user_id}
└─ Returns: {
   "identity_key",
   "signed_prekey",
   "signed_prekey_signature",
   "prekey_id",
   "one_time_prekey" (or None)
}
```

### Messages Endpoints (`messages.py`)

```python
Function: send_message(
    recipient_id: int,
    sealed_blob: str (b64),
    message_number: int,
    ttl_seconds: int | None
) → dict
├─ POST /messages/send
└─ Returns: {"id", ...}

Function: fetch_inbox() → list[dict]
├─ GET /messages/inbox
└─ Returns: [{
   "id": int,
   "sender_id": int,
   "sealed_blob": str (b64),
   "message_number": int,
   ...
}]

Function: fetch_conversation(other_user_id: int) → list[dict]
├─ GET /messages/conversation/{other_user_id}
└─ Returns: Conversation history

Function: confirm_delivery(message_id: int) → dict
├─ DELETE /messages/{message_id}/confirm
└─ Returns: {"status", ...}
```

### WebSocket (`ws.py`)
```
Status: Empty file (infrastructure, not yet used)
```

## 2.6 Cryptography - `client/crypto/`

### Keys (`keys.py`)

```python
Function: generate_identity_keypair() → dict
├─ Generate X25519 DH keypair
├─ Generate Ed25519 signing keypair
└─ Returns: {
   "dh_private": bytes,
   "dh_public": bytes,
   "signing_private": bytes,
   "signing_public": bytes
}

Function: generate_signed_prekey(signing_private_key_bytes: bytes) → dict
├─ Input: Ed25519 signing private key
├─ Generate X25519 prekey pair
├─ Sign prekey public with signing_private
└─ Returns: {
   "private": bytes,
   "public": bytes,
   "signature": bytes
}

Function: generate_one_time_prekeys(count: int = 10) → list[dict]
├─ Generate 'count' X25519 keypairs
└─ Returns: [{"private": bytes, "public": bytes}, ...] × count

Function: encode_public_key(raw_bytes: bytes) → str
└─ Returns: base64 encoded string

Function: decode_public_key(b64_str: str) → bytes
└─ Returns: decoded bytes
```

### X3DH (`x3dh.py`)

```python
Function: x3dh_sender(
    ik_a_private: bytes,
    ik_b_public: bytes,
    spk_b_public: bytes,
    opk_b_public: bytes | None
) → dict

X3DH Algorithm (Sender Side):
├─ Generate ephemeral keypair: ek_a
├─ Perform DH exchanges:
│  ├─ dh1 = ik_a.exchange(spk_b)
│  ├─ dh2 = ek_a.exchange(ik_b)
│  ├─ dh3 = ek_a.exchange(spk_b)
│  └─ dh4 = ek_a.exchange(opk_b) [if opk_b]
├─ Concatenate: dh_input = dh1 + dh2 + dh3 [+ dh4]
├─ Derive shared secret: HKDF-SHA256(dh_input)
└─ Return: {
   "shared_secret": bytes(32),
   "ek_public": bytes(32)
}

Function: x3dh_receiver(
    ik_b_private: bytes,
    spk_b_private: bytes,
    ik_a_public: bytes,
    ek_a_public: bytes,
    opk_b_private: bytes | None
) → bytes (shared_secret)

X3DH Algorithm (Receiver Side):
├─ Perform DH exchanges (inverse of sender):
│  ├─ dh1 = spk_b.exchange(ik_a)
│  ├─ dh2 = ik_b.exchange(ek_a)
│  ├─ dh3 = spk_b.exchange(ek_a)
│  └─ dh4 = opk_b.exchange(ek_a) [if opk_b]
├─ Concatenate: dh_input = dh1 + dh2 + dh3 [+ dh4]
├─ Derive shared secret: HKDF-SHA256(dh_input)
└─ Return: shared_secret (same as sender's)
```

### Ratchet (`ratchet.py`)

```python
Dataclass: RatchetState

Fields:
├─ root_key: bytes (32)
├─ sending_chain_key: bytes (32)
├─ recv_chain_key: bytes (32)
├─ dh_sending_private: bytes (32)
├─ dh_sending_public: bytes (32)
├─ dh_remote_public: bytes (32)
├─ send_count: int
├─ recv_count: int
└─ skipped_message_keys: dict (for out-of-order msgs)

Helper: _hkdf(salt, input_key) → (key, chain)
Helper: _gen_dh_keypair() → (priv, pub)
Helper: _dh(priv_bytes, pub_bytes) → shared_secret

Function: init_ratchet_sender(shared_secret: bytes, recipient_ratchet_public: bytes) → RatchetState
├─ Initialize ratchet for sender side
└─ Returns: RatchetState with initialized chains

Function: init_ratchet_receiver(shared_secret: bytes, our_ratchet_private: bytes) → RatchetState
├─ Initialize ratchet for receiver side
└─ Returns: RatchetState with initialized chains

Function: derive_message_key(chain_key: bytes) → (msg_key, next_chain)
├─ msg_key = HMAC-SHA256(chain_key, b"\x01")
├─ next_chain = HMAC-SHA256(chain_key, b"\x02")
└─ Returns: (msg_key, next_chain)

Function: dh_ratchet_step(state: RatchetState, their_new_public: bytes) → RatchetState
├─ Called when receiving message with new DH public
├─ Performs DH ratchet: updating root, send, recv chains
├─ Generates new ephemeral DH keypair
└─ Resets counters and skipped keys

Function: ratchet_encrypt(state: RatchetState, plaintext: bytes) → (header_dict, ciphertext)
├─ Derive message key from sending_chain_key
├─ Advance chain_key and send_count
├─ Encrypt plaintext with AES-256-GCM
├─ Return: (header_dict, nonce[12] + encrypted)
└─ Header: {"dh_public": b64, "send_count", "recv_count"}

Function: ratchet_decrypt(state: RatchetState, header: dict, ciphertext: bytes) → bytes
├─ Check if remote DH public changed
│  └─ If changed: perform dh_ratchet_step()
├─ If message out-of-order:
│  ├─ Check skipped_message_keys cache
│  └─ Raise error if not found
├─ Advance recv_chain_key to match sender's send_count
│  └─ Store intermediate keys for future out-of-order
├─ Decrypt with AES-256-GCM
└─ Return: plaintext bytes
```

### Sealed Sender (`sealed_sender.py`)

```python
Function: seal(
    sender_id: int,
    sender_ik_public: bytes,
    recipient_ik_public: bytes,
    ciphertext: bytes,
    header: dict
) → bytes (sealed_blob)

Sealed Sender Algorithm:
├─ Generate ephemeral keypair: ek
├─ Perform ECDH with recipient's identity key
├─ Derive encryption key: HKDF-SHA256(dh_out)
├─ Create inner JSON:
│  {
│    "sender_id": int,
│    "sender_ik_public": b64(...),
│    "ciphertext": b64(...),
│    "header": {...}
│  }
├─ Encrypt inner JSON with AES-256-GCM
└─ Return: ek_public[32] + nonce[12] + encrypted[...]

Function: unseal(
    recipient_ik_private: bytes,
    sealed_blob: bytes
) → dict (inner_object)

Unseal Algorithm:
├─ Extract components:
│  ├─ ek_public = first 32 bytes
│  ├─ nonce = next 12 bytes
│  └─ encrypted = remaining
├─ Perform ECDH to recover encryption key
├─ Decrypt inner JSON with AES-256-GCM
└─ Return: Parsed inner object
```

## 2.7 Services - `client/services/`

### High-Level Messaging (`messaging.py`)

```python
Helper Functions:
├─ b64e(data: bytes) → str
│  └─ base64.b64encode()
│
└─ b64d(data: str) → bytes
   └─ base64.b64decode()

Function: send(
    recipient_id: int,
    plaintext: str,
    storage_password: str,
    ttl_seconds: int | None
) → dict (server response)

COMPLETE SEND PIPELINE:

1. Load my keys
   └─ load_keys(storage_password)
   └─ Extract: user_id, ik_private, ik_public, signing_private

2. Check existing session
   └─ load_session(recipient_id, password)
   └─ If exists, verify recipient's keys haven't rotated

3. If NEW session: X3DH
   ├─ fetch_key_bundle(recipient_id)
   │  └─ Get recipient's public keys
   │
   ├─ x3dh_sender(...)
   │  └─ Compute shared_secret and ek_public
   │
   └─ init_ratchet_sender(...)
      └─ Initialize ratchet with shared_secret

4. Encrypt with Double Ratchet
   ├─ ratchet_encrypt(state, plaintext)
   │  └─ Returns: (header, nonce+ciphertext)
   │
   └─ Store X3DH data in header if new session

5. Seal for anonymity
   ├─ seal(
   │    sender_id, my_ik_public, recipient_ik_public,
   │    ciphertext, header
   │  )
   │  └─ Returns: ek_public + nonce + encrypted

6. Send to server
   ├─ api_send(
   │    recipient_id,
   │    sealed_blob=b64(sealed_bytes),
   │    message_number,
   │    ttl_seconds
   │  )
   │  └─ POST /messages/send

7. Save session
   ├─ save_session(recipient_id, state, password)
   │  └─ Serialize ratchet state
   │  └─ Encrypt and persist locally

8. Return server response

Function: receive(storage_password: str) → list[dict]

COMPLETE RECEIVE PIPELINE:

1. Load my keys
   ├─ load_keys(password)
   ├─ my_ik_private, my_spk_private
   └─ one_time_prekeys lookup dict

2. Fetch messages from server
   └─ fetch_inbox()
   └─ GET /messages/inbox

3. For each encrypted message:

   3a. Unseal
       ├─ unseal(my_ik_private, sealed_blob)
       └─ Extract: sender_id, sender_ik_public, ciphertext, header

   3b. Check for X3DH (new session indicator)
       ├─ If x3dh_data in header:
       │  ├─ NEW SESSION
       │  ├─ x3dh_receiver(...)
       │  │  └─ Compute shared_secret
       │  │
       │  └─ init_ratchet_receiver(shared_secret)
       │     └─ Initialize receiver ratchet
       │
       └─ Else: EXISTING SESSION
           ├─ load_session(sender_id, password)
           └─ If None: Skip (can't decrypt)

   3c. Decrypt with Double Ratchet
       ├─ ratchet_decrypt(state, header, ciphertext)
       └─ Returns: plaintext_bytes

   3d. Save updated session
       └─ save_session(sender_id, state, password)

   3e. Confirm delivery
       └─ confirm_delivery(msg_id)
       └─ DELETE /messages/{msg_id}/confirm

   3f. Add to results
       ├─ sender_id
       ├─ plaintext
       ├─ message_id
       └─ message_number

4. Return results list
```

## 2.8 Storage - `client/storage/`

### Keystore (`keystore.py`)

```python
Helper: _derive_key(password: str, salt: bytes) → bytes(32)
├─ PBKDF2-HMAC-SHA256(iterations=480000)
└─ Derives encryption key

Helper: _encrypt(data: bytes, password: str) → bytes
├─ Generate: salt (16) + nonce (12)
├─ Derive key
├─ AES-256-GCM encrypt
└─ Return: salt + nonce + ciphertext

Helper: _decrypt(data: bytes, password: str) → bytes
├─ Extract: salt, nonce, ciphertext
├─ Derive key
├─ AES-256-GCM decrypt
└─ On failure: Raise StorageError("Wrong password or corrupted file")

Function: save_keys(keys: dict, password: str = None) → None
├─ password = password or settings.STORAGE_PASSWORD
├─ Serialize keys to JSON
├─ Encrypt with _encrypt()
├─ Save to: .fortrx/keys_{user_id}.enc (per-user)
└─ Legacy fallback: .fortrx/keys.enc

Function: load_keys(password: str = None) → dict
├─ Try: .fortrx/keys_{current_user_id}.enc
├─ Fallback: .fortrx/keys.enc
├─ Fallback: any single keys_*.enc
├─ Decrypt and parse JSON
└─ Return: keys dict

Function: keys_exist() → bool
├─ Check if any key file exists
└─ Return: True | False

Function: load_keys_or_exit(password: str = None) → dict | Exits
├─ Try: load_keys()
├─ Catch StorageError: Print error, exit(1)
└─ Return: keys dict
```

### Session Store (`session_store.py`)

```python
Helper: _b64e(b: bytes | None) → str | None
Helper: _b64d(s: str | None) → bytes | None

Function: serialize_state(state: RatchetState) → dict
├─ Convert all bytes fields to base64
└─ Return: JSON-serializable dict

Function: deserialize_state(data: dict) → RatchetState
├─ Convert all base64 fields back to bytes
└─ Reconstruct RatchetState

Function: save_sessions(sessions: dict, password: str = None) → None
├─ Serialize to JSON
├─ Encrypt with keystore._encrypt()
├─ Save to: .fortrx/sessions.enc

Function: load_sessions(password: str = None) → dict
├─ Load and decrypt sessions file
├─ Parse JSON
└─ Return: {str(user_id): serialized_state, ...}

Function: save_session(other_user_id: int, state: RatchetState, password: str) → None
├─ Load all sessions
├─ Update sessions[str(user_id)] with serialized state
└─ Save all

Function: load_session(other_user_id: int, password: str = None) → RatchetState | None
├─ Load all sessions
├─ If str(user_id) in sessions:
│  └─ Deserialize and return
└─ Else: return None
```

### Token Store (`token_store.py`)

```python
Function: save_token(token: str) → None
├─ Create .fortrx/ directory
├─ Write token as plain text to .fortrx/token
└─ WARNING: NOT ENCRYPTED

Function: load_token() → str | None
├─ Read .fortrx/token
└─ Return: token or None

Function: delete_token() → None
├─ Delete .fortrx/token if exists

Function: load_and_set_token() → bool
├─ Load token from disk
├─ If exists: api.set_token(token)
└─ Return: True if set, False otherwise
```

## 2.9 Tests - `tests/`

### Test Encoding (`test_encoding.py`)

```python
Test: test_session_serialize_deserialize_roundtrip()
├─ Create dummy RatchetState
├─ Serialize to dict
├─ Deserialize back
└─ Assert: fields match

Test: test_seal_unseal_roundtrip()
├─ Generate X25519 keypairs
├─ Seal with specific data
├─ Unseal with corresponding key
└─ Assert: Data integrity
```

### Test Ratchet (`test_ratchet.py`)

```python
Helper: make_state_with_chain(chain_key, dh_pub) → RatchetState

Test: test_derive_message_key_consistency()
├─ Derive same chain key twice
└─ Assert: Deterministic

Test: test_encrypt_decrypt_pair()
├─ Encrypt plaintext
├─ Decrypt ciphertext
└─ Assert: Plaintext matches

Test: test_multiple_messages_ordered()
├─ Encrypt 3 messages
├─ Decrypt all in order
└─ Assert: All correct
```

---

# PART 3: INTEGRATION FLOWS

## 3.1 Registration Flow

```
CLIENT                              SERVER
  │                                  │
  ├─── register cmd ─────────────────→
  │    └─ username, email, password   │
  │                                  │
  │  Check availability               │
  │  └─ Get username uniqueness      │
  │  └─ Get email uniqueness         │
  │                                  │
  │  Hash password (bcrypt)          │
  │                                  │
  │  Create user record              │
  │                                  │
  ←─── UserResponse ─────────────────┤
       └─ {id, username, email}       │
```

## 3.2 Login & Key Initialization Flow

```
CLIENT                              SERVER
  │                                  │
  ├─── login ────────────────────────→
  │    └─ username, password         │
  │                                  │
  │  Verify credentials              │
  │  └─ Get user                     │
  │  └─ Verify password              │
  │                                  │
  │  Create JWT token                │
  │                                  │
  ←─── JWT token ────────────────────┤
       └─ exp: 30 minutes              │
       
  Save token locally
  └─ .fortrx/token
  
  ├─── init (generate keys) ────────→
  │    └─ (no payload)               │
  │                                  │
  Generate locally:                  
  ├─ Identity keypair (X25519 + Ed25519)
  ├─ Signed prekey (X25519 + signature)
  └─ 10x One-time prekeys (X25519)   
  
  ├─── upload key bundle ───────────→
  │    └─ identity_key (b64)         │
  │    └─ signed_prekey (b64)        │
  │    └─ signed_prekey_signature    │
  │    └─ one_time_prekeys: [...]    │
  │                                  │
  │  Store in key_bundles table      │
  │  Update user.identity_public_key │
  │                                  │
  ←─── Success ───────────────────────┤
  
  Save keys locally (encrypted)
  └─ .fortrx/keys_{user_id}.enc
     └─ PBKDF2 + AES-256-GCM
```

## 3.3 Message Send Flow (Complete Encryption)

```
CLIENT                              SERVER
  │                                  │
User: fortrx send-cmd 2 "hello"      │
  │                                  │
Load sender keys                     │
├─ ~/.fortrx/keys_{my_id}.enc       │
└─ Decrypt with storage password    │
   ├─ my_identity_private           │
   ├─ my_identity_public            │
   └─ signing_private               │
                                    │
Load/create session                 │
├─ if exists: verify keys match     │
├─ if new:                          │
│  ├─── fetch_key_bundle(2) ───────→
│  │    └─ Get recipient's keys     │
│  │                                │
│  │  Parse response:               │
│  │  ├─ identity_key               │
│  │  ├─ signed_prekey              │
│  │  ├─ signed_prekey_signature    │
│  │  └─ one_time_prekey (popped)   │
│  │                                │
│  ←─── KeyBundleResponse ──────────┤
│                                    │
│  X3DH (Initial Key Agreement)      │
│  ├─ Send: ik_a, ik_b, spk_b, otpk_b
│  │         → Compute shared_secret│
│  ├─ Recv: spk_b, ik_b, ek_a, otpk_b
│  │        → Compute shared_secret │
│  └─ Both: shared_secret matches!  │
│                                    │
│  Create ratchet from shared_secret │
│  └─ root_key, chain_keys, DH keys │
│                                    │
Encrypt message                      │
├─ ratchet_encrypt(state, plaintext)│
│  ├─ Derive msg_key from chain     │
│  ├─ AES-256-GCM(msg_key, "hello") │
│  └─ Return: header + ciphertext   │
│                                    │
Seal message (anonymous sender)      │
├─ seal(sender_id, my_ik_pub, ...  │
│       recipient_ik_pub, ...)     │
│  ├─ Generate ephemeral keypair   │
│  ├─ ECDH with recipient ik_pub   │
│  ├─ Encrypt: {sender_id, ...}    │
│  └─ Return: sealed_blob          │
│                                    │
├─ send_message ──────────────────→
│  └─ sealed_blob (b64)             │
│  └─ message_number (ratchet count)│
│                                    │
│  Store message blob:              │
│  ├─ Upload to S3/MinIO            │
│  ├─ Generate blob_key             │
│  └─ Save blob metadata in DB      │
│                                    │
│  Notify recipient (if online):    │
│  ├─ Redis pub/sub                 │
│  └─ WebSocket (if connected)      │
│                                    │
←─ MessageResponse ─────────────────┤
   └─ {id, message_number, ...}    │
                                    │
Save ratchet state locally          │
└─ ~/.fortrx/sessions.enc          │
   └─ Encrypted with storage pwd   │
   └─ Points to recipient_id=2     │
```

## 3.4 Message Receive Flow (Complete Decryption)

```
CLIENT                              SERVER
  │                                  │
User: fortrx inbox                   │
  │                                  │
Load receiver keys                   │
├─ my_identity_private              │
├─ my_signed_prekey_private         │
├─ my_one_time_prekeys (lookup)     │
                                    │
├─── fetch_inbox ───────────────────→
│    └─ GET /messages/inbox         │
│                                    │
│  Query messages WHERE recipient_id│
│  = my_id                          │
│                                    │
│  For each message:                │
│  ├─ Download blob from S3         │
│  ├─ Base64 encode                 │
│  └─ Return in response            │
│                                    │
←─── list[MessageResponse] ─────────┤
     └─ [{id, sealed_blob(b64), ...}]
                                    │
For each message:                   │
│                                    │
Unseal (recover sender info)        │
├─ unseal(my_ik_private, blob)     │
│  ├─ Extract ek_public, nonce     │
│  ├─ ECDH to recover key          │
│  ├─ AES-256-GCM decrypt          │
│  └─ Parse JSON: {sender_id, ...} │
│                                    │
Check for X3DH (new session?)       │
├─ If x3dh in header:               │
│  ├─ NEW SESSION                   │
│  ├─ X3DH receiver:                │
│  │  ├─ my_ik_private              │
│  │  ├─ my_spk_private             │
│  │  ├─ sender_ik_public           │
│  │  ├─ sender_ek_public           │
│  │  └─ my_one_time_prekey_private │
│  │     → Compute shared_secret    │
│  │                                │
│  ├─ init_ratchet_receiver         │
│  │  └─ Create ratchet from secret │
│  │                                │
│  └─ Save to new session           │
│                                    │
└─ Else:                            │
   ├─ EXISTING SESSION              │
   └─ load_session(sender_id, pwd)  │
   └─ If None: Skip (error)         │
                                    │
Decrypt with ratchet                │
├─ ratchet_decrypt(state, header,  │
│                  ciphertext)      │
│  ├─ Handle out-of-order msgs     │
│  ├─ Advance chain keys            │
│  ├─ AES-256-GCM decrypt          │
│  └─ Return: plaintext            │
│                                    │
Save ratchet session                │
└─ ~/.fortrx/sessions.enc          │
                                    │
├─── confirm_delivery ──────────────→
│    └─ DELETE /messages/{id}/confirm
│                                    │
│  Delete blob from S3              │
│  Delete message record from DB    │
│                                    │
←─── Success ───────────────────────┤
                                    │
Display:                            │
├─ From: sender_id                  │
├─ Message: plaintext               │
├─ Status: ✔️ delivered             │
└─ Msg #: message_number            │
```

---

# PART 4: DATABASE SCHEMA

## 4.1 Users Table

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username VARCHAR UNIQUE NOT NULL,
  email VARCHAR UNIQUE NOT NULL,
  hashed_password VARCHAR NOT NULL,
  identity_public_key VARCHAR,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  is_active BOOLEAN DEFAULT 1
);

Indexes:
├─ PRIMARY KEY: id
├─ UNIQUE: username
├─ UNIQUE: email
└─ None on identity_public_key
```

## 4.2 Messages Table

```sql
CREATE TABLE messages (
  id INTEGER PRIMARY KEY,
  recipient_id INTEGER NOT NULL,
  sealed_blob VARCHAR NOT NULL,  -- S3 blob key
  message_number INTEGER,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME
);

Indexes:
├─ PRIMARY KEY: id
└─ implicit on recipient_id (for WHERE filters)

Data Flow:
├─ sealed_blob = S3 key reference (not actual data)
├─ Actual encrypted data stored in S3/MinIO
└─ expires_at triggers background cleanup job
```

## 4.3 Key Bundles Table

```sql
CREATE TABLE key_bundles (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  identity_key TEXT,
  signed_prekey TEXT,
  signed_prekey_signature TEXT,
  prekey_id INTEGER,
  one_time_prekeys TEXT,  -- JSON array string
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

Indexes:
├─ PRIMARY KEY: id
└─ INDEX: user_id (for lookups)

Storage Notes:
├─ one_time_prekeys: JSON serialized because SQLite lacks array type
├─ Each key is base64 encoded
├─ On fetch: one OTP is popped (consumed for anti-replay)
└─ On lookup failure: 404 Not Found
```

---

# PART 5: API ROUTES COMPLETE

## 5.1 Authentication Routes

```
POST /auth/register
├─ Rate: 5/minute
├─ Body: { "username": str, "email": str, "password": str }
├─ Response: 201 Created
│   { "id": int, "username": str, "email": str, "created_at": datetime }
└─ Errors: 400, 422

POST /auth/login
├─ Rate: 10/minute
├─ Body: form-encoded { "username": str, "password": str }
├─ Response: 200 OK
│   { "access_token": str, "token_type": "bearer" }
├─ Errors: 401 Unauthorized

GET /auth/me
├─ Auth: Bearer token (required)
├─ Response: 200 OK
│   { "id": int, "username": str, "email": str, "is_active": bool, "created_at": datetime }
└─ Errors: 401
```

## 5.2 Keys Routes

```
POST /keys/upload
├─ Auth: Bearer token (required)
├─ Body: {
│    "identity_key": str (base64),
│    "signed_prekey": str (base64),
│    "signed_prekey_signature": str (base64),
│    "prekey_id": int,
│    "one_time_prekeys": [str, ...] (list of base64)
│  }
├─ Response: 201 Created
│   { "message": "Key bundle uploaded successfully" }
└─ Errors: 401, 422

GET /keys/{user_id}
├─ Auth: Bearer token (required)
├─ Path: { "user_id": int }
├─ Response: 200 OK
│   {
│     "user_id": int,
│     "identity_key": str (base64),
│     "signed_prekey": str (base64),
│     "signed_prekey_signature": str (base64),
│     "prekey_id": int,
│     "one_time_prekey": str (base64) | null
│   }
└─ Errors: 401, 404
```

## 5.3 Messages Routes

```
POST /messages/send
├─ Auth: Bearer token (required)
├─ Body: {
│    "recipient_id": int,
│    "sealed_blob": str (base64),
│    "message_number": int,
│    "ttl_seconds": int (optional)
│  }
├─ Response: 201 Created
│   {
│     "id": int,
│     "recipient_id": int,
│     "message_number": int,
│     "sealed_blob": str (S3 key),
│     "created_at": datetime,
│     "expires_at": datetime | null
│   }
└─ Errors: 401, 404 (recipient not found), 422

GET /messages/inbox
├─ Auth: Bearer token (required)
├─ Response: 200 OK
│   [
│     {
│       "id": int,
│       "recipient_id": int,
│       "message_number": int,
│       "sealed_blob": str (base64 data),
│       "created_at": datetime,
│       "expires_at": datetime | null
│     },
│     ...
│   ]
└─ Errors: 401

DELETE /messages/{message_id}/confirm
├─ Auth: Bearer token (required)
├─ Path: { "message_id": int }
├─ Response: 200 OK
│   { "message": "deleted" }
├─ Errors: 401, 403 (not owner)
└─ Side Effect: Deletes blob from S3, removes DB record
```

## 5.4 WebSocket Routes

```
WebSocket /ws/{user_id}
├─ Auth: token query parameter (required)
├─ Path: { "user_id": int }
├─ Connection: 
│  ├─ Verify token.sub == user_id
│  ├─ Accept connection
│  ├─ Subscribe to Redis channel
│  └─ Listen for messages
│
├─ Messages from client → server:
│  └─ "ping" responses with "pong"
│
├─ Messages from server → client (via Redis):
│  ├─ Type: "new_message"
│  ├─ Contains: message_id, message_number, expires_at
│  └─ Delivery: When sender posts message
│
└─ On disconnect: Cleanup connections
```

---

# PART 6: DEPENDENCY TREE

## 6.1 Server Dependencies (Fortress)

```
run.py
  ↓
uvicorn
  ↓
app/main.py (FastAPI)
  │
  ├─ routers/
  │  ├─ auth → services/auth_service → repositories/user_repo → models/user
  │  ├─ keys → services/key_service → repositories/key_repo → models/key_bundle
  │  ├─ messages → services/message_service → repositories/message_repo
  │  ├─ ws → services/connection_manager → services/pubsub → redis
  │  └─ safety (placeholder)
  │
  ├─ services/
  │  ├─ auth_service → crypto/tokens, crypto/hashing
  │  ├─ key_service → repositories
  │  ├─ message_service → storage_service → S3/MinIO → boto3
  │  ├─ storage_service → boto3, redis
  │  └─ connection_manager, pubsub → redis
  │
  ├─ crypto/
  │  ├─ tokens → python-jose, datetime
  │  ├─ hashing → passlib, bcrypt
  │  ├─ keys, x3dh, ratchet, sealed_sender → cryptography library
  │  └─ fingerprint (placeholder)
  │
  ├─ database.py → sqlalchemy
  │
  └─ middleware/
     ├─ rate_limit → slowapi, limits
     └─ security_headers → fastapi

External Libraries:
├─ fastapi, uvicorn
├─ sqlalchemy, psycopg2, alembic
├─ boto3 (S3)
├─ redis
├─ cryptography
├─ python-jose
├─ passlib, bcrypt
├─ slowapi (rate limiting)
├─ pydantic
├─ websockets
```

## 6.2 Client Dependencies (Fortrx-Client)

```
run.py
  ↓
client/main.py (Typer CLI)
  │
  ├─ commands/
  │  ├─ register → network/auth → network/api
  │  ├─ login → network/auth → storage/token_store
  │  ├─ send → services/messaging → network/keys, network/messages
  │  ├─ inbox → services/messaging
  │  ├─ init → (key gen & upload)
  │  ├─ verify (stub)
  │  └─ purge → network/messages
  │
  ├─ network/
  │  ├─ api.py → httpx
  │  ├─ auth.py → api
  │  ├─ keys.py → api
  │  ├─ messages.py → api
  │  └─ ws.py (empty)
  │
  ├─ services/
  │  └─ messaging.py
  │     ├─ crypto/x3dh, crypto/ratchet, crypto/sealed_sender
  │     ├─ storage/session_store, storage/keystore
  │     ├─ network/keys, network/messages
  │     └─ Full E2E pipeline orchestration
  │
  ├─ crypto/
  │  ├─ keys.py → cryptography library
  │  ├─ x3dh.py → cryptography library
  │  ├─ ratchet.py → cryptography library, hmac
  │  └─ sealed_sender.py → cryptography library, json
  │
  └─ storage/
     ├─ keystore.py → cryptography, json
     ├─ session_store.py → keystore, json
     └─ token_store.py → pathlib

External Libraries:
├─ typer, rich (CLI)
├─ httpx (HTTP client)
├─ cryptography
├─ python-dotenv
├─ pydantic
```

---

# PART 7: ALL FUNCTIONS REFERENCE

## 7.1 Server Functions Index

### Main Application
- `run.py`: uvicorn.run() → Starts server
- `app/main.py`: FastAPI app, lifespan, expired_message_cleanup()
- `app/config.py`: Settings class (Pydantic)
- `app/database.py`: create_engine(), SessionLocal(), get_db()

### Routers
- `auth.py`: register(), login(), get_me()
- `keys.py`: upload_keys(), get_keys()
- `messages.py`: send_message(), get_inbox(), confirm_delivery()
- `ws.py`: websocket_endpoint()
- `safety.py`: (placeholder)

### Services
- `auth_service.py`: register_user(), login_user()
- `key_service.py`: upload_key_bundle(), fetch_key_bundle()
- `message_service.py`: send_message(), fetch_inbox(), confirm_delivery(), purge_expired_messages()
- `storage_service.py`: get_s3_client(), ensure_bucket_exists(), generate_blob_key(), upload_blob(), download_blob(), delete_blob()
- `connection_manager.py`: ConnectionManager class (connect, disconnect, send_to_user, is_online)
- `pubsub.py`: get_redis(), publish_message(), subscribe_to_user(), unsubscribe_from_user()

### Repositories
- `user_repo.py`: get_user_by_id(), get_user_by_username(), get_user_by_email(), create_user()
- `message_repo.py`: save_message(), get_message_for_user(), delete_message(), get_expired_messages()
- `key_repo.py`: get_bundle_by_user_id(), create_bundle(), update_bundle(), pop_one_time_prekey()

### Cryptography
- `hashing.py`: hash_password(), verify_password()
- `tokens.py`: create_access_token(), decode_access_token(), create_token_for_user()
- `keys.py`: (same as client)
- `x3dh.py`: (same as client)
- `ratchet.py`: (same as client)
- `sealed_sender.py`: (same as client)

### Dependencies & Middleware
- `dependencies/auth.py`: get_current_user(), get_active_user()
- `middleware/rate_limit.py`: limiter (Limiter instance)
- `middleware/security_headers.py`: SecurityHeadersMiddleware

---

## 7.2 Client Functions Index

### Main Application
- `run.py`: app() entry
- `client/main.py`: Typer app, startup callback

### Commands
- `register.py`: register()
- `login.py`: login()
- `send.py`: send_cmd()
- `inbox.py`: inbox()
- `init.py`: init()
- `verify.py`: verify()
- `purge.py`: purge()

### Network
- `api.py`: set_token(), get_token(), _headers(), get(), post(), delete(), raise_for_status(), FortrxAPIError
- `auth.py`: register(), login(), get_me()
- `keys.py`: upload_key_bundle(), fetch_key_bundle()
- `messages.py`: send_message(), fetch_inbox(), fetch_conversation(), confirm_delivery()

### Services
- `messaging.py`: send(), receive(), b64e(), b64d(), encode_header()

### Cryptography
- `keys.py`: generate_identity_keypair(), generate_signed_prekey(), generate_one_time_prekeys(), encode_public_key(), decode_public_key()
- `x3dh.py`: _hkdf_derive(), x3dh_sender(), x3dh_receiver()
- `ratchet.py`: RatchetState, _hkdf(), _gen_dh_keypair(), _dh(), init_ratchet_sender(), init_ratchet_receiver(), derive_message_key(), dh_ratchet_step(), ratchet_encrypt(), ratchet_decrypt()
- `sealed_sender.py`: _json_safe(), seal(), unseal()

### Storage
- `keystore.py`: _derive_key(), _encrypt(), _decrypt(), save_keys(), load_keys(), keys_exist(), load_keys_or_exit()
- `session_store.py`: _b64e(), _b64d(), serialize_state(), deserialize_state(), save_sessions(), load_sessions(), save_session(), load_session()
- `token_store.py`: save_token(), load_token(), delete_token(), load_and_set_token()

### Tests
- `test_encoding.py`: test_session_serialize_deserialize_roundtrip(), test_seal_unseal_roundtrip()
- `test_ratchet.py`: make_state_with_chain(), test_derive_message_key_consistency(), test_encrypt_decrypt_pair(), test_multiple_messages_ordered()

---

## 7.3 File Storage Layout

```
Client Local Storage:

.fortrx/
├── token                    # Plain text JWT (⚠️ not encrypted)
├── keys.enc                 # Legacy encrypted keys file
├── keys_{user_id}.enc       # Per-user encrypted keys (preferred)
└── sessions.enc             # Encrypted session state (all convos)

Server S3 Storage:

messages/{recipient_id}/{timestamp}_{random}.enc
├─ Each message's sealed blob stored separately
├─ Referenced by blob_key in messages DB table
└─ Deleted on confirm_delivery()
```

---

# SECURITY ANALYSIS

## Encryption Strengths

✅ **E2E Encryption**: Signal Protocol (X3DH + Double Ratchet)  
✅ **Forward Secrecy**: Ratchet algorithm ensures old keys can't decrypt new messages  
✅ **Identity Keys**: X25519 (32 bytes = 256-bit security)  
✅ **Message Encryption**: AES-256-GCM  
✅ **HKDF Derivation**: SHA-256 based  
✅ **Password Storage**: PBKDF2 (480k iterations) + bcrypt  
✅ **Anti-Replay**: One-time prekeys on first message  
✅ **Anonymous Sender**: Sealed Sender wrapping (identity encryption)  
✅ **Out-of-Order Handling**: Ratchet supports message reordering  

## Potential Concerns

⚠️ **Token Storage**: JWT tokens stored in plain text on client  
⚠️ **Server Sees Metadata**: Message counts, timestamps, user IDs  
⚠️ **No Identity Verification**: No built-in fingerprint verification  
⚠️ **Session Loss**: If session file deleted, old messages unrecoverable  
⚠️ **Blob Storage**: S3 blobs not individually encrypted (trust S3 security)  

---

# DEPLOYMENT NOTES

## Fortress Server Requirements

```
Services:
├─ PostgreSQL (or SQLite for testing)
├─ Redis (pub/sub, rate limiting)
├─ S3/MinIO (message blob storage)
└─ FastAPI/Uvicorn (HTTP server)

Configuration (.env):
├─ DATABASE_URL=postgresql://...
├─ SECRET_KEY=<random-secret>
├─ S3_ENDPOINT_URL=...
├─ S3_ACCESS_KEY=...
├─ S3_SECRET_KEY=...
├─ S3_BUCKET_NAME=fortrx-messages
├─ REDIS_URL=redis://...
└─ RATE_LIMIT_STORAGE=redis://...

Docker Compose Stack:
├─ PostgreSQL container
├─ Redis container
├─ MinIO container
└─ Fortress (Uvicorn) container
```

## Fortrx Client Requirements

```
Runtime:
├─ Python 3.9+
├─ pip packages (cryptography, httpx, typer, etc.)
└─ .fortrx/ directory (auto-created)

User Workflow:
1. fortrx register alice alice@example.com
2. fortrx login alice
3. fortrx init (generates 30+ cryptographic keys)
4. fortrx send-cmd <recipient_id> <message>
5. fortrx inbox (decrypt all messages)
```

---

# KEY INSIGHTS

## Architecture Summary

```
┌─────────────────────────────────┐
│   Fortrx Client (CLI)           │
│  - Typer command-line app       │
│  - Generates keypairs locally   │
│  - Performs all encryption      │
│  - Stores encrypted state       │
└────────────┬────────────────────┘
             │
             │ HTTPS REST API
             │
┌────────────▼────────────────────┐
│   Fortress Server               │
│  - FastAPI endpoint             │
│  - User & key management        │
│  - Message routing via S3       │
│  - WebSocket notifications      │
└─────────────────────────────────┘
             │
    ┌────────┼────────┬───────────┐
    │        │        │           │
    ▼        ▼        ▼           ▼
PostgreSQL Redis  S3/MinIO   WebSocket
(Users)  (PubSub) (Blobs)    (Notify)
```

## Data Flow Summary

**Send**: Client → Encrypt (X3DH + Ratchet + Seal) → Upload S3 → Notify recipient

**Receive**: Download S3 → Unseal (recover identity) → Decrypt (Ratchet) → Display locally

**Init**: Generate 30 keys locally → Encrypt with password → Save .fortrx/ → Upload public keys to server

---

*Complete Generated Map - April 5, 2026*  
*All 100+ functions, classes, and structures documented*  
*Ready for MCP integration and new chat context*
