from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_image_api_rejects_multipart_without_500():
    response = client.post(
        "/api/v1/desensitize/image",
        files={"file": ("sample.png", b"not-an-image", "image/png")},
    )

    assert response.status_code == 415
    assert "application/json" in response.json()["detail"]
    assert "multipart/form-data is not supported" in response.json()["detail"]


def test_image_api_json_validation_still_returns_422():
    response = client.post("/api/v1/desensitize/image", json={})

    assert response.status_code == 422
