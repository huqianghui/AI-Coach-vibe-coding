"""Dev-only reverse proxy that injects an Entra ID (AAD) bearer token.

Purpose
-------
The Azure AI Foundry resource used in local development has API-key authentication
disabled (``disableLocalAuth=true``), so it only accepts Entra ID tokens. The
prompt-optimizer sidecar's ``custom`` provider can only send a *static* API key,
which cannot satisfy Entra-only auth (AAD tokens expire ~hourly).

This proxy sits between the optimizer and the real Azure OpenAI endpoint:

    optimizer --(dummy key)--> aoai_aad_proxy --(fresh AAD bearer)--> Azure OpenAI

It fetches/refreshes a token via ``DefaultAzureCredential`` (picks up ``az login``,
a service principal, or a managed identity) and forwards every request upstream
with a valid ``Authorization: Bearer`` header.

NOT for production. Production should use managed identity end-to-end.

Usage
-----
    AOAI_UPSTREAM_BASE=https://ai-foundry-svc2.services.ai.azure.com \
    AOAI_PROXY_PORT=8199 \
    python scripts/aoai_aad_proxy.py

Then point the optimizer at ``http://host.docker.internal:8199/openai/v1`` with any
placeholder key.
"""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from azure.identity import DefaultAzureCredential

UPSTREAM_BASE = os.environ.get(
    "AOAI_UPSTREAM_BASE", "https://ai-foundry-svc2.services.ai.azure.com"
).rstrip("/")
PROXY_PORT = int(os.environ.get("AOAI_PROXY_PORT", "8199"))
TOKEN_SCOPE = os.environ.get("AOAI_TOKEN_SCOPE", "https://cognitiveservices.azure.com/.default")
# Refresh the cached token this many seconds before it actually expires.
_REFRESH_SKEW = 300

_credential = DefaultAzureCredential()
_token_lock = threading.Lock()
_cached_token: str | None = None
_cached_exp: float = 0.0

# Hop-by-hop / auth headers we must not forward from the client.
_STRIP_REQUEST_HEADERS = {
    "host",
    "authorization",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "api-key",
}
_STRIP_RESPONSE_HEADERS = {
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "content-encoding",
}


def _get_token() -> str:
    """Return a valid AAD access token, refreshing shortly before expiry."""
    import time

    global _cached_token, _cached_exp
    with _token_lock:
        if _cached_token is None or time.time() >= _cached_exp - _REFRESH_SKEW:
            tok = _credential.get_token(TOKEN_SCOPE)
            _cached_token = tok.token
            _cached_exp = tok.expires_on
        return _cached_token


_client = httpx.Client(timeout=120.0)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401 - quiet by default
        return

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""

        url = f"{UPSTREAM_BASE}{self.path}"
        fwd_headers = {
            k: v for k, v in self.headers.items() if k.lower() not in _STRIP_REQUEST_HEADERS
        }
        fwd_headers["Authorization"] = f"Bearer {_get_token()}"

        try:
            upstream = _client.request(self.command, url, headers=fwd_headers, content=body)
        except Exception as exc:  # noqa: BLE001 - surface upstream failure to client
            msg = f'{{"error":{{"code":"proxy_error","message":{exc!r}}}}}'.encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        self.send_response(upstream.status_code)
        for k, v in upstream.headers.items():
            if k.lower() not in _STRIP_RESPONSE_HEADERS:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(upstream.content)))
        self.end_headers()
        self.wfile.write(upstream.content)

    # All methods route through the same proxy logic.
    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_PATCH = _proxy


def main() -> None:
    # Fail fast if we cannot obtain a token at startup.
    _get_token()
    server = ThreadingHTTPServer(("0.0.0.0", PROXY_PORT), _Handler)
    print(
        f"aoai_aad_proxy listening on :{PROXY_PORT} -> {UPSTREAM_BASE} (scope={TOKEN_SCOPE})",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
