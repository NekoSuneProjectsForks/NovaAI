"""NovaAI - live stream-alert sources (Streamlabs + StreamElements).

Both platforms push alerts over Socket.IO. We use the optional ``python-socketio``
client (install with ``pip install -r requirements-streaming.txt``) and degrade
gracefully when it's missing or no token is set — the generic ``/webhook/stream``
endpoint and the in-app simulator still work without any of this.

Each source runs in its own daemon thread, normalizes incoming payloads into a
``StreamEvent`` via ``stream_events``, and hands it to an ``on_event`` callback
(``Api.handle_stream_event``).
"""
from __future__ import annotations

import base64
import binascii
import json
import threading
from typing import Callable

from . import stream_events

try:
    import socketio  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    socketio = None  # type: ignore

try:
    import websocket as _websocket  # websocket-client (raw WS for SE Astro)
except Exception:  # pragma: no cover - optional dependency
    _websocket = None  # type: ignore

STREAMLABS_URL = "https://sockets.streamlabs.com"
STREAMELEMENTS_URL = "https://realtime.streamelements.com"
STREAMELEMENTS_ASTRO_URL = "wss://astro.streamelements.com/"


def available() -> bool:
    """True when the optional Socket.IO client library is installed."""
    return socketio is not None


def _jwt_channel(token: str) -> str:
    """Best-effort: pull the channel/account id out of a StreamElements JWT.

    SE channel JWTs carry the channel id in their (unsigned-readable) payload,
    so we can subscribe to the right Astro room without asking for it twice.
    """
    try:
        parts = (token or "").split(".")
        if len(parts) < 2:
            return ""
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8", "ignore"))
        return str(
            data.get("channel")
            or data.get("channelId")
            or data.get("channel_id")
            or data.get("provider_id")
            or ""
        )
    except (ValueError, binascii.Error, KeyError):
        return ""


class _BaseSource:
    name = "source"

    def __init__(
        self,
        token: str,
        on_event: Callable[["stream_events.StreamEvent"], None],
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.token = (token or "").strip()
        self.on_event = on_event
        self.on_status = on_status or (lambda _m: None)
        self._client = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _deps_ok(self) -> bool:
        """Whether this source's client library is installed (override per source)."""
        return socketio is not None

    def start(self) -> bool:
        if not self.token:
            return False
        if not self._deps_ok():
            self.on_status(
                f"{self.name}: streaming client not installed — run "
                "'pip install -r requirements-streaming.txt' to enable live alerts."
            )
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"Nova{self.name}")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._client is not None:
                self._client.disconnect()
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _emit(self, events) -> None:
        for ev in events if isinstance(events, list) else [events]:
            if ev is not None:
                try:
                    self.on_event(ev)
                except Exception:
                    pass

    def _run(self) -> None:  # pragma: no cover - needs live token
        raise NotImplementedError


class StreamlabsSource(_BaseSource):
    name = "Streamlabs"

    def _run(self) -> None:  # pragma: no cover - needs live token
        sio = socketio.Client(reconnection=True, logger=False, engineio_logger=False)
        self._client = sio

        @sio.event
        def connect() -> None:
            self.on_status("Streamlabs: connected.")

        @sio.event
        def disconnect() -> None:
            self.on_status("Streamlabs: disconnected.")

        @sio.on("event")
        def _on_event(data) -> None:
            self._emit(stream_events.from_streamlabs(data or {}))

        try:
            sio.connect(
                f"{STREAMLABS_URL}?token={self.token}",
                transports=["websocket"],
            )
            sio.wait()
        except Exception as exc:
            self.on_status(f"Streamlabs: connection failed ({exc}).")


class StreamElementsSocketIOSource(_BaseSource):
    """Legacy StreamElements realtime gateway (Socket.IO). Kept as a fallback.

    Prefer :class:`StreamElementsAstroSource` (the current Astro WS gateway).
    """

    name = "StreamElements"

    def _run(self) -> None:  # pragma: no cover - needs live token
        sio = socketio.Client(reconnection=True, logger=False, engineio_logger=False)
        self._client = sio

        @sio.event
        def connect() -> None:
            # StreamElements requires authenticating with the JWT after connect.
            try:
                sio.emit("authenticate", {"method": "jwt", "token": self.token})
            except Exception:
                pass

        @sio.event
        def authenticated(_data=None) -> None:
            self.on_status("StreamElements: authenticated.")

        @sio.event
        def disconnect() -> None:
            self.on_status("StreamElements: disconnected.")

        @sio.on("event")
        def _on_event(data) -> None:
            ev = stream_events.from_streamelements(data or {})
            self._emit([ev] if ev else [])

        @sio.on("event:test")
        def _on_event_test(data) -> None:
            ev = stream_events.from_streamelements(data or {})
            self._emit([ev] if ev else [])

        try:
            sio.connect(STREAMELEMENTS_URL, transports=["websocket"])
            sio.wait()
        except Exception as exc:
            self.on_status(f"StreamElements: connection failed ({exc}).")


class StreamElementsAstroSource(_BaseSource):
    """StreamElements Astro WebSocket gateway (wss://astro.streamelements.com).

    Subscribes to ``channel.tips`` (donations) and ``channel.activities``
    (follows/subs/cheers/raids/hosts/gift subs/Super Chats) for the channel the
    JWT belongs to, and supports zero-downtime reconnect tokens.
    """

    name = "StreamElements"
    TOPICS = ("channel.activities", "channel.tips")

    def _deps_ok(self) -> bool:
        return _websocket is not None

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._client is not None:
                self._client.close()
        except Exception:
            pass

    def _run(self) -> None:  # pragma: no cover - needs live token
        room = _jwt_channel(self.token)
        if not room:
            self.on_status(
                "StreamElements: couldn't read the channel id from the JWT — "
                "check that you pasted a channel JWT token."
            )
            return

        reconnect_token = ""

        def on_open(ws) -> None:
            # On a fresh connection we subscribe; after a graceful reconnect the
            # server restores subscriptions automatically (re-subscribing is a
            # harmless no-op, so we always send them).
            for topic in self.TOPICS:
                try:
                    ws.send(json.dumps({
                        "type": "subscribe",
                        "nonce": topic,
                        "data": {
                            "topic": topic,
                            "room": room,
                            "token": self.token,
                            "token_type": "jwt",
                        },
                    }))
                except Exception:
                    pass

        def on_message(ws, raw) -> None:
            nonlocal reconnect_token
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                return
            mtype = msg.get("type")
            if mtype == "welcome":
                self.on_status("StreamElements: connected (Astro).")
            elif mtype == "response" and msg.get("error"):
                detail = (msg.get("data") or {}).get("message", "")
                self.on_status(f"StreamElements: {msg.get('error')} {detail}".strip())
            elif mtype == "message":
                ev = stream_events.from_streamelements_astro(msg)
                self._emit([ev] if ev else [])
            elif mtype == "reconnect":
                reconnect_token = str((msg.get("data") or {}).get("reconnect_token") or "")
                try:
                    ws.close()
                except Exception:
                    pass

        def on_error(ws, err) -> None:
            self.on_status(f"StreamElements: ws error ({err}).")

        # Reconnect loop: honor graceful reconnect tokens, otherwise back off.
        while not self._stop.is_set():
            url = STREAMELEMENTS_ASTRO_URL
            if reconnect_token:
                url = f"{STREAMELEMENTS_ASTRO_URL}?reconnect_token={reconnect_token}"
                reconnect_token = ""
            ws = _websocket.WebSocketApp(
                url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
            )
            self._client = ws
            try:
                # Server pings every 30s; websocket-client auto-replies with pong.
                ws.run_forever(ping_timeout=60)
            except Exception as exc:
                self.on_status(f"StreamElements: connection failed ({exc}).")
            if self._stop.is_set():
                break
            self._stop.wait(5)  # brief backoff before reconnecting


# Default StreamElements source is the current Astro gateway.
StreamElementsSource = StreamElementsAstroSource
