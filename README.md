# Fortrx Client

Encrypted terminal client for the Fortrx messaging system.

This client is built around:
- end-to-end encrypted messaging with X3DH / PQXDH-style session bootstrap
- local-first chat history stored in an encrypted client database
- a background daemon for inbox sync, live delivery, and presence updates
- offline reading of already-synced conversations

## Features

- Encrypted key initialization and local private-key storage
- Local chat history and conversation summaries
- Background daemon for sync and WebSocket listening
- Contacts and conversation overview
- Offline chat viewing with `--no-sync`
- Self-messaging stored locally as `Saved Messages`

## Requirements

- Python 3.11+
- A running Fortrx server
- Redis enabled on the server for live delivery and presence
- SQLCipher Python bindings are preferred for encrypted local storage

## Server Selection

Production defaults to `https://fortrx-server.duckdns.org`.

For local development, create `.env.local` with:

```powershell
SERVER_URL=http://localhost:8000
```

You can also point the client at a different stack by setting `FORTRX_ENV_FILE` to an alternate env file path before running commands.

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Quick Start

1. Log in:

```powershell
py run.py login <username> --password <account_password> --storage-password <local_storage_password>
```

2. Initialize keys once:

```powershell
py run.py init --password <local_storage_password>
```

3. Start the background daemon:

```powershell
py run.py daemon start --password <local_storage_password>
```

4. Send a message:

```powershell
py run.py send <recipient_id> "hello" --password <local_storage_password>
```

5. View conversations:

```powershell
py run.py contacts --password <local_storage_password>
py run.py inbox --password <local_storage_password>
py run.py chat <contact_id> --password <local_storage_password>
```

## Common Commands

Authentication and setup:

```powershell
py run.py register <username> <email> --password <account_password>
py run.py login <username> --password <account_password> --storage-password <local_storage_password>
py run.py init --password <local_storage_password>
py run.py verify <user_id> --password <local_storage_password>
```

Messaging:

```powershell
py run.py send <recipient_id> "message" --password <local_storage_password>
py run.py inbox --password <local_storage_password>
py run.py contacts --password <local_storage_password>
py run.py chat <contact_id> --password <local_storage_password>
py run.py chat <contact_id> --password <local_storage_password> --before 2026-04-08T10:00:00+00:00
```

Daemon and sync:

```powershell
py run.py daemon start --password <local_storage_password>
py run.py daemon run --password <local_storage_password>
py run.py daemon status
py run.py daemon stop
```

Offline usage:

```powershell
py run.py contacts --password <local_storage_password> --no-sync
py run.py inbox --password <local_storage_password> --no-sync
py run.py chat <contact_id> --password <local_storage_password> --no-sync
```

## Local Storage Model

The client stores data in `.fortrx/fortrx.db` by default.

The database contains:
- encrypted auth token storage
- private keys
- ratchet sessions
- message history
- conversation summaries
- presence cache
- verification data

Already-synced messages can be read offline. New messages still require the server.

## Notes

- Sending to yourself does not go through the server. Those messages are stored locally as `Saved Messages`.
- `contacts` is the fastest overview command for large histories because it uses conversation summaries instead of scanning all messages.
- `inbox` marks listed conversations as viewed.
- `chat <contact_id>` marks only that conversation as viewed.

## Development

Run a quick compile sanity check:

```powershell
@'
import compileall
print(compileall.compile_dir("client", quiet=1))
'@ | python -
```

Run tests:

```powershell
pytest
```

## Related Files

- CLI entrypoint: [run.py](/c:/Users/himan/Documents/GitHub/Fortrx-Client/run.py)
- Main app: [client/main.py](/c:/Users/himan/Documents/GitHub/Fortrx-Client/client/main.py)
- Local DB layer: [client/storage/db.py](/c:/Users/himan/Documents/GitHub/Fortrx-Client/client/storage/db.py)
- Messaging flow: [client/services/messaging.py](/c:/Users/himan/Documents/GitHub/Fortrx-Client/client/services/messaging.py)
- Daemon: [client/services/daemon.py](/c:/Users/himan/Documents/GitHub/Fortrx-Client/client/services/daemon.py)
