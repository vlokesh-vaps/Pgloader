from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
def test_health(): assert client.get("/api/health").json()["status"] == "ok"
def test_metadata(): assert client.get("/api/source/tables?schema=dbo").json()["schema"] == "dbo"
def test_validation_rejects_empty_tables():
    response = client.post("/api/migrations/preflight", json={"source": {"database_type":"sqlserver","host":"a","port":1433,"database":"a","username":"u","password":"p"}, "destination": {"database_type":"postgresql","host":"b","port":5432,"database":"b","username":"u","password":"p"}, "schema":"dbo","tables":[]})
    assert response.status_code == 422
