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

import threading
from typing import Callable

from . import stream_events

try:
    import socketio  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    socketio = None  # type: ignore

STREAMLABS_URL = "https://sockets.streamlabs.com"
STREAMELEMENTS_URL = "https://realtime.streamelements.com"


def available() -> bool:
    """True when the optional Socket.IO client library is installed."""
    return socketio is not None


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

    def start(self) -> bool:
        if not self.token:
            return False
        if not available():
            self.on_status(
                f"{self.name}: python-socketio not installed — run "
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


class StreamElementsSource(_BaseSource):
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
