import httpx
import pytest
from fastapi.testclient import TestClient

from cqa.backend.config import Settings
from cqa.backend.main import create_app
from cqa.backend.models import Conversation
from cqa.backend.services.audio_recording import (
    MAX_RESPONSE_BYTES,
    MEDIA_HOST,
    PLAYER_HOST,
    bounded_range,
    trusted_url,
)

PLAYER = f"https://{PLAYER_HOST}/player?sig=private-player-signature"
MEDIA = f"https://{MEDIA_HOST}/recording?sig=private-media-signature"


def make_app(tmp_path, handler, url=PLAYER):
    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'audio.db'}", llm_provider="mock"),
        worker_enabled=False,
        transport=httpx.MockTransport(handler),
    )
    app.state.db.initialize()
    with app.state.db.sessions.begin() as session:
        session.add(
            Conversation(
                conversation_id="call-1",
                dataset_group_id="SYNTHETIC",
                channel="voice call",
                language="RU",
                audio_url=url,
                original_payload={},
            )
        )
    return app


def test_actual_player_shape_resolves_audio_and_preserves_range(tmp_path):
    requests = []

    def upstream(request):
        requests.append(request)
        if request.url.host == PLAYER_HOST:
            return httpx.Response(
                200,
                text=(
                    f'<html><audio controls><source src="{MEDIA}" type="audio/mpeg"></audio></html>'
                ),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return httpx.Response(
            206,
            content=b"\xff\xf3fake-mp3",
            headers={
                "content-type": "audio/mpeg",
                "content-range": "bytes 100-109/2000",
                "accept-ranges": "bytes",
            },
        )

    with TestClient(make_app(tmp_path, upstream)) as client:
        response = client.get("/api/conversations/call-1/audio", headers={"Range": "bytes=100-109"})
        assert response.status_code == 206
        assert response.content == b"\xff\xf3fake-mp3"
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.headers["content-range"] == "bytes 100-109/2000"
        assert response.headers["cache-control"] == "private, no-store"
        assert all(r.headers["range"] == "bytes=100-109" for r in requests)
        assert "signature" not in str(response.headers)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "https://169.254.169.254/latest/meta-data",
        f"https://{MEDIA_HOST}.evil.test/audio",
        f"https://user:password@{MEDIA_HOST}/audio",
        f"https://{MEDIA_HOST}:444/audio",
        f"https://{MEDIA_HOST}/audio#fragment",
    ],
)
def test_untrusted_stored_sources_never_make_network_requests(tmp_path, url):
    def upstream(request):
        pytest.fail("Untrusted recording caused a network request")

    assert not trusted_url(url)
    with TestClient(make_app(tmp_path, upstream, url)) as client:
        response = client.get("/api/conversations/call-1/audio")
        assert response.status_code == 422
        assert url not in response.text


@pytest.mark.parametrize(
    "status,headers,body,expected",
    [
        (302, {"location": "http://127.0.0.1/private"}, b"", 502),
        (200, {"content-type": "text/html"}, b"<html>login</html>", 502),
        (200, {"content-type": "application/octet-stream"}, b"unknown", 502),
        (200, {"content-type": "text/html"}, b"x" * (65536 + 1), 502),
        (200, {"content-type": "audio/mpeg", "content-length": "30000000"}, b"", 413),
        (200, {"content-type": "audio/mpeg", "content-length": "5000000"}, b"", 502),
    ],
)
def test_invalid_upstream_fails_safely(tmp_path, status, headers, body, expected):
    def upstream(request):
        return httpx.Response(status, headers=headers, content=body)

    with TestClient(make_app(tmp_path, upstream)) as client:
        response = client.get("/api/conversations/call-1/audio")
        assert response.status_code == expected
        assert "private-player-signature" not in response.text


def test_wrapper_cannot_point_at_untrusted_host(tmp_path):
    count = 0

    def upstream(request):
        nonlocal count
        count += 1
        return httpx.Response(
            200,
            text='<audio><source src="https://127.0.0.1/private"></audio>',
            headers={"content-type": "text/html"},
        )

    with TestClient(make_app(tmp_path, upstream)) as client:
        assert client.get("/api/conversations/call-1/audio").status_code == 502
    assert count == 1


def test_range_limits_missing_recording_and_upstream_timeout(tmp_path):
    requests = []

    def upstream(request):
        requests.append(request)
        raise httpx.ReadTimeout("secret upstream URL")

    assert bounded_range(None) == f"bytes=0-{MAX_RESPONSE_BYTES - 1}"
    assert bounded_range("bytes=20-") == f"bytes=20-{20 + MAX_RESPONSE_BYTES - 1}"
    assert bounded_range("bytes=-9000000") == f"bytes=-{MAX_RESPONSE_BYTES}"
    with TestClient(make_app(tmp_path, upstream)) as client:
        assert client.get("/api/conversations/unknown/audio").status_code == 404
        assert (
            client.get(
                "/api/conversations/call-1/audio", headers={"Range": "bytes=0-1,4-5"}
            ).status_code
            == 416
        )
        assert (
            client.get(
                "/api/conversations/call-1/audio", headers={"Range": "bytes=9-2"}
            ).status_code
            == 416
        )
        assert not requests
        response = client.get("/api/conversations/call-1/audio")
        assert response.status_code == 502
        assert "secret" not in response.text
        assert requests[0].headers["range"] == f"bytes=0-{MAX_RESPONSE_BYTES - 1}"


def test_upstream_unsatisfiable_range_is_forwarded_without_signed_urls(tmp_path):
    def upstream(request):
        return httpx.Response(416, headers={"content-range": "bytes */2000"})

    with TestClient(make_app(tmp_path, upstream, MEDIA)) as client:
        response = client.get("/api/conversations/call-1/audio", headers={"Range": "bytes=9999-"})
        assert response.status_code == 416
        assert response.headers["content-range"] == "bytes */2000"
        assert not response.content


@pytest.mark.parametrize("content_range", ["bytes 0-19/2000", "bytes 9-2/2000", "bad"])
def test_inconsistent_media_ranges_are_rejected(tmp_path, content_range):
    def upstream(request):
        return httpx.Response(
            206,
            content=b"0123456789",
            headers={"content-type": "audio/mpeg", "content-range": content_range},
        )

    with TestClient(make_app(tmp_path, upstream, MEDIA)) as client:
        assert client.get("/api/conversations/call-1/audio").status_code == 502
