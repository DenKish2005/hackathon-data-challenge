"""Stream stored organizer recordings, including its HTML player wrapper.

Only the two organizer-controlled HTTPS origins are accepted. The endpoint takes
a conversation ID, never a caller-provided URL, and never returns signed URLs.
"""

import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from cqa.backend.models import Conversation

PLAYER_HOST = "ec88f21f1accecf38e20095a9fe175.a5.environment.api.powerplatform.com"
MEDIA_HOST = "freedomholdingcorporation.crm11.dynamics.com"
MAX_HTML_BYTES = 64 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024  # Fits the Vercel function response limit.
STREAM_SECONDS = 90
RANGE = re.compile(r"bytes=(?:\d+-\d*|-\d+)\Z")


def bounded_range(value):
    if not value:
        return f"bytes=0-{MAX_RESPONSE_BYTES - 1}"
    start, end = value.removeprefix("bytes=").split("-", 1)
    if not start:
        if int(end) == 0:
            raise HTTPException(416, "Invalid byte range")
        return f"bytes=-{min(int(end), MAX_RESPONSE_BYTES)}"
    first = int(start)
    last = min(int(end), first + MAX_RESPONSE_BYTES - 1) if end else first + MAX_RESPONSE_BYTES - 1
    if last < first:
        raise HTTPException(416, "Invalid byte range")
    return f"bytes={first}-{last}"


def trusted_url(value):
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname in (PLAYER_HOST, MEDIA_HOST)
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
        )
    except (TypeError, ValueError):
        return False


class AudioSource(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.source = None
        self.in_audio = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "audio":
            self.in_audio = True
        if self.source is None and self.in_audio and tag in ("audio", "source"):
            self.source = attrs.get("src")

    def handle_endtag(self, tag):
        if tag == "audio":
            self.in_audio = False


async def open_audio(client, url, byte_range):
    """Return a validated open media response; close every intermediate body."""
    if not trusted_url(url):
        raise HTTPException(422, "Recording source is not supported")
    headers = {"Accept": "audio/*,text/html;q=0.5", "Accept-Encoding": "identity"}
    if byte_range:
        headers["Range"] = byte_range
    response = await client.send(client.build_request("GET", url, headers=headers), stream=True)
    try:
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if response.status_code == 200 and content_type == "text/html":
            # Wrappers may ignore Range. Read a small bounded document, not an arbitrary page.
            if urlsplit(url).hostname != PLAYER_HOST:
                raise HTTPException(502, "Recording source did not return audio")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_HTML_BYTES:
                    raise HTTPException(502, "Recording player response is too large")
            parser = AudioSource()
            parser.feed(body.decode("utf-8", errors="replace"))
            source = urljoin(url, parser.source or "")
            if not trusted_url(source) or urlsplit(source).hostname != MEDIA_HOST:
                raise HTTPException(502, "Recording player has no supported audio source")
            await response.aclose()
            response = await client.send(
                client.build_request("GET", source, headers=headers), stream=True
            )
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if response.status_code == 416:
            return response
        if response.status_code not in (200, 206) or not content_type.startswith("audio/"):
            raise HTTPException(502, "Recording source did not return audio")
        if response.status_code == 206:
            match = re.fullmatch(
                r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", "")
            )
            if not match:
                raise HTTPException(502, "Invalid recording byte range")
            first, last, total = map(int, match.groups())
            if first > last or last >= total:
                raise HTTPException(502, "Invalid recording byte range")
        try:
            length = int(response.headers.get("content-length", "0"))
            total = response.headers.get("content-range", "").rsplit("/", 1)[-1]
            total = int(total) if total.isdigit() else 0
        except ValueError as exc:
            raise HTTPException(502, "Invalid recording response") from exc
        if length < 0 or max(length, total) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Recording exceeds the 25 MB playback limit")
        if not length or length > MAX_RESPONSE_BYTES:
            raise HTTPException(502, "Recording source did not honor the playback byte limit")
        if response.status_code == 206 and length != last - first + 1:
            raise HTTPException(502, "Invalid recording byte range length")
        return response
    except BaseException:
        await response.aclose()
        raise


def install_audio(app, db, transport=None):
    @app.get("/api/conversations/{conversation_id}/audio")
    async def recording(conversation_id: str, request: Request):
        with db.sessions() as session:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None or not conversation.audio_url:
                raise HTTPException(404, "Recording not available")
            url = conversation.audio_url
        byte_range = request.headers.get("range")
        if byte_range and (len(byte_range) > 80 or not RANGE.fullmatch(byte_range)):
            raise HTTPException(416, "Only a single byte range is supported")
        client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(20, connect=10),
            follow_redirects=False,
        )
        try:
            async with asyncio.timeout(30):
                upstream = await open_audio(client, url, bounded_range(byte_range))
        except HTTPException:
            await client.aclose()
            raise
        except (httpx.HTTPError, TimeoutError):
            await client.aclose()
            raise HTTPException(502, "Recording source unavailable") from None
        except BaseException:
            await client.aclose()
            raise
        headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
        for key in ("content-length", "content-range", "accept-ranges"):
            if key in upstream.headers:
                headers[key] = upstream.headers[key]
        if upstream.status_code == 416:
            await upstream.aclose()
            await client.aclose()
            headers.pop("content-length", None)
            return Response(status_code=416, headers=headers)

        async def chunks():
            size = 0
            try:
                async with asyncio.timeout(STREAM_SECONDS):
                    async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            return
                        yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(
            chunks(),
            status_code=upstream.status_code,
            media_type=upstream.headers["content-type"],
            headers=headers,
        )
