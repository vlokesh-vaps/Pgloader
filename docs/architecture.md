# Architecture

The React client owns presentation, wizard state, and client-side validation. It never connects to either database. FastAPI owns validation, metadata adapters, preflight, job state, audit boundaries, and process orchestration.

`PgloaderService` is the only process boundary. It invokes the installed `pgloader` binary with `asyncio.create_subprocess_exec` and never uses a shell. Credential-bearing `.load` files are created under a `0700` job directory with `0600` permissions and removed after execution.

The in-memory job repository is intentional for the first runnable slice. Replace it with SQLAlchemy repositories and a durable worker queue before multi-process production deployment. The service and API contracts are already separated for that change.
