"""NovaAI - Twitch chat ingestion.

A minimal Twitch IRC client using only the standard library (socket + ssl), so
it stays in the project's threaded model without pulling in an async stack.
It connects to a channel, reads chat messages, and hands each one to a
callback. It can read anonymously (no token) or authenticate to also send
messages back to chat.

Follows the daemon-thread pattern used elsewhere (see
``Api.start_reminder_checker`` in ``webgui.py``): one background thread reads
the socket and never crashes the app.
"""
from __future__ import annotations

import re
import socket
import ssl
import threading
from typing import Callable

TWITCH_HOST = "irc.chat.twitch.tv"
TWITCH_PORT = 6697

# :nick!nick@nick.tmi.twitch.tv PRIVMSG #channel :message text
_PRIVMSG_RE = re.compile(
    r"^(?:@(?P<tags>[^ ]*) )?:(?P<nick>[^!]+)![^ ]+ PRIVMSG #(?P<chan>[^ ]+) :(?P<msg>.*)$"
)


class TwitchClient:
    def __init__(
        self,
        channel: str,
        on_message: Callable[[str, str], None],
        bot_username: str | None = None,
        oauth_token: str | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.channel = channel.strip().lstrip("#").lower()
        self.on_message = on_message
        self.on_status = on_status or (lambda _msg: None)
        self.bot_username = (bot_username or "").strip().lower()
        self.oauth_token = (oauth_token or "").strip()
        self.authenticated = bool(self.oauth_token and self.bot_username)

        self._sock: ssl.SSLSocket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = False

    # ── public API ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not self.channel:
            raise RuntimeError("No Twitch channel configured.")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="NovaAITwitch", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._connected = False
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception:
            pass
        self._sock = None

    def is_connected(self) -> bool:
        return self._connected

    def send_message(self, text: str) -> bool:
        """Send a chat message (requires authentication). Returns success."""
        if not self.authenticated or self._sock is None or not self._connected:
            return False
        safe = text.replace("\r", " ").replace("\n", " ").strip()
        if not safe:
            return False
        try:
            self._raw(f"PRIVMSG #{self.channel} :{safe}")
            return True
        except Exception:
            return False

    # ── internals ─────────────────────────────────────────────────────────────

    def _raw(self, line: str) -> None:
        assert self._sock is not None
        self._sock.sendall((line + "\r\n").encode("utf-8"))

    def _connect(self) -> None:
        context = ssl.create_default_context()
        raw_sock = socket.create_connection((TWITCH_HOST, TWITCH_PORT), timeout=20)
        self._sock = context.wrap_socket(raw_sock, server_hostname=TWITCH_HOST)
        self._sock.settimeout(1.0)

        if self.authenticated:
            token = self.oauth_token
            if not token.lower().startswith("oauth:"):
                token = "oauth:" + token
            self._raw(f"PASS {token}")
            self._raw(f"NICK {self.bot_username}")
        else:
            # Anonymous read-only login.
            self._raw("NICK justinfan12345")
        self._raw(f"JOIN #{self.channel}")
        self._connected = True
        mode = "authenticated" if self.authenticated else "read-only"
        self.on_status(f"Connected to #{self.channel} ({mode}).")

    def _run(self) -> None:
        backoff = 2.0
        buffer = ""
        while not self._stop.is_set():
            try:
                if self._sock is None:
                    self._connect()
                    backoff = 2.0
                try:
                    data = self._sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    raise ConnectionError("socket closed")
                if not data:
                    raise ConnectionError("connection closed by server")
                buffer += data.decode("utf-8", errors="ignore")
                while "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)
                    self._handle_line(line)
            except Exception as exc:
                self._connected = False
                try:
                    if self._sock is not None:
                        self._sock.close()
                except Exception:
                    pass
                self._sock = None
                if self._stop.is_set():
                    break
                self.on_status(f"Disconnected ({exc}). Reconnecting...")
                self._stop.wait(backoff)
                backoff = min(30.0, backoff * 1.5)
        self._connected = False
        self.on_status("Twitch client stopped.")

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        if line.startswith("PING"):
            payload = line.split(" ", 1)[1] if " " in line else ":tmi.twitch.tv"
            try:
                self._raw(f"PONG {payload}")
            except Exception:
                pass
            return
        match = _PRIVMSG_RE.match(line)
        if not match:
            return
        nick = match.group("nick")
        message = match.group("msg").strip()
        if nick and message:
            try:
                self.on_message(nick, message)
            except Exception:
                pass
