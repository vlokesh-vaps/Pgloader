# Migration flow

The wizard enforces Source/Destination → Schema/Tables → Options → Preflight/Review. The start action submits only after client validation, server preflight, and explicit destructive confirmation when `drop_tables` is enabled.

Jobs return immediately with a unique ID. An async task consumes pgloader output, appends structured logs, and transitions through `STARTING`, `RUNNING`, and a terminal state. Replace the in-process task registry with a durable queue and SSE/WebSocket broadcaster for multi-worker production deployment.
