# Security Policy

## Supported Versions

Security fixes are best-effort for the latest version of this client in the default branch.

## Reporting a Vulnerability

Please do not open public issues for security-sensitive problems.

Report vulnerabilities privately with:
- a clear description of the issue
- impact and affected flow
- reproduction steps if available
- whether private keys, tokens, or message history may be exposed

If you are maintaining this repository publicly, add a private security contact here, for example:
- GitHub Security Advisories
- a dedicated security email address
- a private issue intake workflow

## Sensitive Areas

Please pay extra attention when reporting problems in:
- local key storage
- SQLCipher / encrypted database handling
- token persistence
- ratchet session storage
- sealed sender logic
- verification and fingerprint flows
- daemon sync and message confirmation ordering

## Operational Guidance

- Never share your local storage password.
- Treat `.fortrx/` as sensitive client state.
- Avoid running the client on untrusted machines.
- Use `--no-sync` if you only need local history while the server is unavailable.
- Rotate credentials and regenerate local state if you suspect device compromise.
