# Local setup

Requirements: Node 20+, Python 3.11+, pgloader v3, and FreeTDS/ODBC drivers when real SQL Server probing is enabled.

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
cd frontend && npm install && npm run dev
```

The UI defaults to `VITE_API_MODE=mock`. Set it to `real` to use FastAPI. The real connection adapters should be configured with pyodbc/psycopg credentials supplied only in request memory or a server-side secret store.
