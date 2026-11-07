import httpx
import pytest
from fastapi.testclient import TestClient

from cqa import api


def records():
    return [
        {
            "conversation_id": "new-chat",
            "channel": "agent chat",
            "language": "RU",
            "transcript": [{"speaker": "operator", "timestamp": "00:01", "text": "Здравствуйте!"}],
        },
        {
            "conversation_id": "new-call",
            "channel": "voice call",
            "language": "KZ",
            "audio_url": "https://audio.example.test/new-call.mp3",
            "transcript": [
                {"speaker": "client", "timestamp": "00:00:03", "text": "Сәлеметсіз бе!"}
            ],
        },
    ]


def install_source(monkeypatch, handler):
    original_client = httpx.AsyncClient
    monkeypatch.setenv(
        "CQA_DATA_URL",
        "https://organizer.example.test/invoke?api-version=1&sig=server-only-test-signature&group_id=OLD",
    )
    monkeypatch.setattr(
        api.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.parametrize("envelope", [True, False])
def test_organizer_fetch_preserves_chat_call_and_server_credentials(monkeypatch, envelope):
    payload = {"isSuccess": True, "data": {"records": records()}} if envelope else records()
    requested = []

    def upstream(request):
        requested.append(request)
        return httpx.Response(200, json=payload)

    install_source(monkeypatch, upstream)
    with TestClient(api.app) as client:
        response = client.get("/api/organizer?group_id=TEAM_3")
    assert response.status_code == 200
    assert response.json() == payload
    assert requested[0].url.params["group_id"] == "TEAM_3"
    assert requested[0].url.params["sig"] == "server-only-test-signature"
    assert "server-only-test-signature" not in response.text


@pytest.mark.parametrize("payload", [None, "unexpected", [], {"isSuccess": False}, {"data": None}])
def test_organizer_bad_source_payload_is_explicit_gateway_error(monkeypatch, payload):
    install_source(monkeypatch, lambda request: httpx.Response(200, json=payload))
    with TestClient(api.app) as client:
        response = client.get("/api/organizer")
    assert response.status_code == 502
    assert "server-only-test-signature" not in response.text


@pytest.mark.parametrize("failure, expected", [("timeout", 504), ("http", 502), ("json", 502)])
def test_organizer_source_failures_do_not_leak_signed_url(monkeypatch, failure, expected):
    def upstream(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("upstream timeout", request=request)
        if failure == "http":
            return httpx.Response(403, text="upstream denied")
        return httpx.Response(200, content=b"not json")

    install_source(monkeypatch, upstream)
    with TestClient(api.app) as client:
        response = client.get("/api/organizer")
    assert response.status_code == expected
    assert "server-only-test-signature" not in response.text
    assert "organizer.example.test" not in response.text


def test_organizer_requires_server_configuration(monkeypatch):
    monkeypatch.delenv("CQA_DATA_URL", raising=False)
    with TestClient(api.app) as client:
        response = client.get("/api/organizer")
    assert response.status_code == 503


@pytest.mark.parametrize(
    "url",
    [
        "http://source.example.test",
        "https://",
        "https://user:pass@source.example.test",
        "https://source.example.test:bad",
    ],
)
def test_organizer_rejects_invalid_server_source_without_leaking_it(monkeypatch, url):
    monkeypatch.setenv("CQA_DATA_URL", url)
    with TestClient(api.app) as client:
        response = client.get("/api/organizer")
    assert response.status_code == 503
    assert "user:pass" not in response.text


def test_organizer_group_id_is_validated_before_fetch(monkeypatch):
    requested = []
    install_source(monkeypatch, lambda request: requested.append(request))
    with TestClient(api.app) as client:
        response = client.get("/api/organizer?group_id=invalid%20group")
    assert response.status_code == 422
    assert requested == []
