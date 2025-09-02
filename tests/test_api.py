from fastapi.testclient import TestClient
from app.api import router

client = TestClient(router)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["ts"], int)

def test_catalog_categories():
    response = client.get("/catalog/categories")
    assert response.status_code == 200
    assert "scheme" in response.json()
    assert "labels" in response.json()

def test_extract():
    payload = {
        "texts": [{"id": "1", "title": "Test", "content": "This is a test content."}],
        "options": {"keywords": {"enable": True, "algo": "yake", "top_k": 10}}
    }
    response = client.post("/extract", json=payload)
    assert response.status_code == 200
    assert "results" in response.json()
