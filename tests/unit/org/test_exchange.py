"""The code exchange's one HTTPS request: verified TLS, no key log, no redirects, no token."""

from __future__ import annotations

import ssl
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from pandoscope.org import releasebot


def tls_context(opener: urllib.request.OpenerDirector) -> ssl.SSLContext:
    (handler,) = [h for h in opener.handlers if isinstance(h, urllib.request.HTTPSHandler)]
    context: ssl.SSLContext = handler._context  # type: ignore[attr-defined]
    return context


@pytest.mark.xfail(strict=True, reason="round 5 V1: no opener of its own yet")
def test_the_exchange_writes_no_tls_key_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path / "keys"))
    context = tls_context(releasebot._opener())
    assert context.keylog_filename is None
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert not (tmp_path / "keys").exists()


@pytest.fixture
def redirecting() -> Iterator[str]:
    """A local server that answers every request with a redirect elsewhere."""

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the http.server hook name
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/elsewhere")
            self.end_headers()

        do_POST = do_GET  # noqa: N815

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Quiet."""

    server = HTTPServer(("127.0.0.1", 0), Redirect)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.xfail(strict=True, reason="round 5 V2: redirects are followed")
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_the_exchange_follows_no_redirect(redirecting: str, method: str) -> None:
    request = urllib.request.Request(redirecting, method=method, data=b"" if method == "POST" else None)
    with pytest.raises(urllib.error.HTTPError) as error:
        releasebot._opener().open(request, timeout=5)
    assert error.value.code == 302


@pytest.mark.xfail(strict=True, reason="round 5: fetch does not go through the opener")
def test_fetch_sends_through_the_opener_without_a_token_and_with_a_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[urllib.request.Request, float]] = []

    class Answer:
        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"ok"

    class Opener:
        def open(self, request: urllib.request.Request, timeout: float) -> Answer:
            sent.append((request, timeout))
            return Answer()

    monkeypatch.setattr(releasebot, "_opener", Opener)
    assert releasebot.fetch("GET", "https://api.github.com/zen") == b"ok"
    ((request, timeout),) = sent
    assert timeout == 30
    assert request.get_header("Authorization") is None
