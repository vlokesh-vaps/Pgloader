# Security model

- Passwords are accepted only by backend request models and are never returned by API responses or logged.
- The browser does not persist connection credentials or contact databases directly.
- pgloader files are server-side, restrictive, temporary, and cleaned up in a `finally` block.
- User values are passed to subprocess execution as arguments; `shell=True` and `os.system` are not used.
- Add authentication, authorization, encrypted secret storage, rate limiting, and durable audit storage before exposing the service beyond a trusted internal network.
