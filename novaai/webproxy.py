"""Reverse-proxy helpers for NovaAI's consolidated ``--web`` port.

In ``--web`` mode every browser-facing service is reached through the *single*
web port, so one origin — and therefore one Cloudflare tunnel hostname on the
standard 443 — serves the whole thing::

    /                         dashboard (served directly)
    /avatar                   avatar overlay page (served directly)
    /avatar-ws                avatar WebSocket bridge   ->  127.0.0.1:8765
    /tts-audio /browser-audio
    /mmd/* /uploads/*         avatar media + VRM files  ->  127.0.0.1:8766
    /mc                       Minecraft live-view dashboard ->  127.0.0.1:8768
    /world/* /inv/* /feed
    /socket.io/*              Minecraft 3D + inventory (HTTP polling + WS)

This is why a tunnel that only forwards 443 used to break: the page hard-coded
``wss://host:8765`` / ``http://host:8766`` and the tunnel had nothing on those
ports. Now those all live under one origin as paths.

Implemented entirely on top of the stdlib ``http.server``:

* normal requests are forwarded over a short-lived upstream socket and the raw
  response is streamed straight back (so chunked / long-poll socket.io bodies
  just flow through);
* a ``Upgrade: websocket`` request hijacks the raw connection, replays the
  handshake to the upstream, then pumps bytes both ways until either side ends.

No third-party dependencies.
"""
from __future__ import annotations

import selectors
import socket
from http import HTTPStatus

# Headers we must not forward verbatim: hop-by-hop, or ones we recompute.
_DROP_REQUEST_HEADERS = {
    "connection",
    "proxy-connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "upgrade",
    "content-length",
    "host",
}

_CONNECT_TIMEOUT = 10.0
_CHUNK = 65536


def is_ws_upgrade(handler) -> bool:
    """True if the current request is a WebSocket handshake."""
    return handler.headers.get("Upgrade", "").strip().lower() == "websocket"


def _read_request_body(handler) -> bytes:
    """Read the inbound request body (Content-Length or chunked)."""
    te = handler.headers.get("Transfer-Encoding", "").lower()
    if "chunked" in te:
        chunks: list[bytes] = []
        while True:
            size_line = handler.rfile.readline().strip()
            if b";" in size_line:
                size_line = size_line.split(b";", 1)[0]
            try:
                size = int(size_line or b"0", 16)
            except ValueError:
                break
            if size == 0:
                # Consume the trailing CRLF (and any trailers) up to the blank line.
                while True:
                    trailer = handler.rfile.readline()
                    if trailer in (b"\r\n", b"\n", b""):
                        break
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.read(2)  # trailing CRLF after each chunk
        return b"".join(chunks)

    try:
        length = int(handler.headers.get("Content-Length", "0") or 0)
    except (TypeError, ValueError):
        length = 0
    return handler.rfile.read(length) if length > 0 else b""


def _build_request(handler, upstream_path: str, host: str, port: int, body: bytes) -> bytes:
    lines = [f"{handler.command} {upstream_path} HTTP/1.1\r\n"]
    for key, value in handler.headers.items():
        if key.lower() in _DROP_REQUEST_HEADERS:
            continue
        lines.append(f"{key}: {value}\r\n")
    lines.append(f"Host: {host}:{port}\r\n")
    lines.append(f"Content-Length: {len(body)}\r\n")
    lines.append("Connection: close\r\n")
    lines.append("\r\n")
    return "".join(lines).encode("latin-1") + body


def proxy_http(handler, target: tuple[str, int], upstream_path: str) -> None:
    """Forward the current HTTP request to ``target`` and stream the reply back.

    The upstream response (status line, headers and body) is relayed verbatim on
    the raw client socket, which transparently handles chunked encoding and the
    open-ended responses socket.io long-polling uses.
    """
    host, port = target
    body = _read_request_body(handler)
    try:
        upstream = socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT)
    except OSError:
        # Upstream (avatar bridge / Minecraft live view) isn't running.
        try:
            handler.send_error(HTTPStatus.BAD_GATEWAY, "Upstream service unavailable")
        except OSError:
            pass
        handler.close_connection = True
        return

    handler.close_connection = True
    try:
        upstream.sendall(_build_request(handler, upstream_path, host, port, body))
        client = handler.connection
        while True:
            chunk = upstream.recv(_CHUNK)
            if not chunk:
                break
            client.sendall(chunk)
    except OSError:
        pass  # either side hung up mid-transfer
    finally:
        try:
            upstream.close()
        except OSError:
            pass


def proxy_ws(handler, target: tuple[str, int], upstream_path: str) -> None:
    """Hijack the connection and bridge a WebSocket to ``target``.

    Replays the handshake (so the upstream sends its own ``101 Switching
    Protocols`` straight back to the browser) and then pumps frames both ways.
    """
    host, port = target
    try:
        upstream = socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT)
    except OSError:
        try:
            handler.send_error(HTTPStatus.BAD_GATEWAY, "Upstream service unavailable")
        except OSError:
            pass
        handler.close_connection = True
        return

    handler.close_connection = True
    lines = [f"GET {upstream_path} HTTP/1.1\r\n"]
    for key, value in handler.headers.items():
        if key.lower() == "host":
            continue
        lines.append(f"{key}: {value}\r\n")
    lines.append(f"Host: {host}:{port}\r\n\r\n")
    try:
        upstream.sendall("".join(lines).encode("latin-1"))
        _pump(handler.connection, upstream)
    except OSError:
        pass
    finally:
        try:
            upstream.close()
        except OSError:
            pass


def _pump(client: socket.socket, upstream: socket.socket) -> None:
    """Relay bytes between two sockets until both directions close."""
    client.setblocking(False)
    upstream.setblocking(False)
    sel = selectors.DefaultSelector()
    sel.register(client, selectors.EVENT_READ, upstream)
    sel.register(upstream, selectors.EVENT_READ, client)
    open_dirs = 2
    try:
        while open_dirs > 0:
            for key, _ in sel.select(timeout=60):
                src: socket.socket = key.fileobj  # type: ignore[assignment]
                dst: socket.socket = key.data
                try:
                    data = src.recv(_CHUNK)
                except BlockingIOError:
                    continue
                except OSError:
                    data = b""
                if not data:
                    try:
                        sel.unregister(src)
                    except (KeyError, ValueError):
                        pass
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    open_dirs -= 1
                    continue
                try:
                    dst.sendall(data)
                except OSError:
                    open_dirs = 0
                    break
    finally:
        sel.close()
