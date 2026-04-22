from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_reports_cpu_model():
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["device"] == "cpu"


def test_offer_rejects_invalid_payload():
    with TestClient(create_app()) as client:
        response = client.post("/offer", json={"sdp": "", "type": "answer"})

    assert response.status_code == 422

