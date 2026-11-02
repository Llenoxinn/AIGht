import fakeredis
import pytest
from fastapi.testclient import TestClient
from aight_api.config import Settings
from aight_api.main import create_app


@pytest.fixture
def environment(tmp_path):
    config = Settings(_env_file=None, data_dir=tmp_path, openai_api_key="synthetic-test-key", chat_model="synthetic-model",
                      notice_version="test-notice", notice_url="https://example.invalid/notice", processor_retention="Test fixture only",
                      processor_region="Test environment", session_provider_tokens=5_000_000)
    app = create_app(config, fakeredis.FakeRedis())
    with TestClient(app) as client:
        yield client, app.state.store


def session(client):
    response = client.post("/api/v1/sessions", json={"processing_notice_version": "test-notice", "accept_processing": True})
    assert response.status_code == 201, response.text
    return response.json(), {"Authorization": "Bearer " + response.json()["session_token"]}


def import_text(client, headers, text="GWA must not exceed 2.00.", key="synthetic-request-0001"):
    response = client.post("/api/v1/documents/text", headers={**headers, "Idempotency-Key": key}, json={"text": text, "title": "Synthetic scholarship"})
    assert response.status_code == 202, response.text
    return response.json()
