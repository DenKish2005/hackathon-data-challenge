"""The unified server imports only explicitly configured organizer groups."""

import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from cqa.api import create_app
from cqa.backend.config import Settings

from .test_foundation_data import dataset_payload


def application(tmp_path, handler, urls=None):
    return create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'source.db'}", organizer_urls=urls or {}),
        transport=httpx.MockTransport(handler),
        worker_enabled=False,
    )


SIGNED_URL = "https://test.environment.api.powerplatform.com/invoke?sig=server-only-test-signature&group_id=DEV"


def test_organizer_preserves_calls_and_verbatim_server_credentials(tmp_path):
    requested = []
    payload = dataset_payload()

    def upstream(request):
        requested.append(str(request.url))
        return httpx.Response(200, json=payload)

    with TestClient(application(tmp_path, upstream, {"DEV": SIGNED_URL})) as client:
        response = client.get("/api/organizer")
        assert response.status_code == 200
        assert response.json() == payload
        assert len(client.get("/api/conversations?channel=voice%20call").json()) == 5
        assert (
            client.get("/api/conversations/synthetic-64").json()["audio_url"]
            == "https://example.test/64.mp3"
        )
    assert requested == [SIGNED_URL]
    assert "server-only-test-signature" not in response.text


@pytest.mark.parametrize("payload", [None, [], {"isSuccess": False}, {"data": None}])
def test_invalid_payload_is_redacted_gateway_error(tmp_path, payload):
    app = application(
        tmp_path, lambda request: httpx.Response(200, json=payload), {"DEV": SIGNED_URL}
    )
    with TestClient(app) as client:
        response = client.get("/api/organizer")
        assert response.status_code == 502
        assert client.get("/api/conversations").json() == []
    assert "server-only-test-signature" not in response.text


def test_mismatched_group_is_not_imported(tmp_path):
    payload = copy.deepcopy(dataset_payload())
    payload["data"]["dataset_group_id"] = "CONTROL"
    with TestClient(
        application(
            tmp_path, lambda request: httpx.Response(200, json=payload), {"DEV": SIGNED_URL}
        )
    ) as client:
        assert client.get("/api/organizer").status_code == 502
        assert client.get("/api/conversations").json() == []


@pytest.mark.parametrize(
    "url",
    [
        "http://source.test",
        "https://untrusted.test",
        "https://user:pass@test.environment.api.powerplatform.com",
    ],
)
def test_untrusted_configuration_is_rejected_before_fetch(tmp_path, url):
    requested = []
    with TestClient(
        application(tmp_path, lambda request: requested.append(request), {"DEV": url})
    ) as client:
        response = client.get("/api/organizer")
        assert response.status_code == 502
    assert not requested
    assert "user:pass" not in response.text


def test_missing_or_unconfigured_group_never_fetches(tmp_path):
    requested = []
    with TestClient(application(tmp_path, lambda request: requested.append(request))) as client:
        assert client.get("/api/organizer").status_code == 404
    assert not requested
