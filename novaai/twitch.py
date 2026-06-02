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

import random
import re
import socket
import ssl
import threading
from typing import Callable

TWITCH_HOST = "irc.chat.twitch.tv"
TWITCH_PORT = 6697

# :nick!nick@nick.tmi.twitch.tv PRIVMSG #channel :message text  (tags optional)
_PRIVMSG_RE = re.compile(
    r"^(?:@(?P<tags>[^ ]*) )?:(?P<nick>[^!]+)![^ ]+ PRIVMSG #(?P<chan>[^ ]+) :(?P<msg>.*)$"
)


def parse_tags(tags: str | None) -> dict[str, str]:
    """Parse an IRCv3 tag string (``key=val;key=val``) into a dict."""
    out: dict[str, str] = {}
    for part in (tags or "").split(";"):
        if "=" in part:
            key, _, val = part.partition("=")
            out[key] = val
    return out


def roles_from_tags(tags: str | None) -> set[str]:
    """Extract chatter roles from message tags (badges + mod/subscriber flags)."""
    t = parse_tags(tags)
    roles: set[str] = set()
    badges = t.get("badges", "")
    badge_names = {b.split("/", 1)[0] for b in badges.split(",") if b}
    if "broadcaster" in badge_names:
        roles.add("broadcaster")
    if t.get("mod") == "1" or "moderator" in badge_names:
        roles.add("moderator")
    if t.get("subscriber") == "1" or badge_names & {"subscriber", "founder"}:
        roles.add("subscriber")
    if "vip" in badge_names:
        roles.add("vip")
    return roles


def normalize_oauth(token: str) -> str:
    """Return a token in Twitch's ``oauth:xxxx`` form, tolerating common pastes."""
    t = (token or "").strip().strip('"').strip("'")
    if not t:
        return ""
    # People paste "oauth:xxx", "oauth: xxx", or just "xxx".
    low = t.lower()
    if low.startswith("oauth:"):
        return "oauth:" + t[6:].strip()
    return "oauth:" + t


class TwitchClient:
    def __init__(
        self,
        channel: str,
        on_message: Callable[[str, str, set[str]], None],
        bot_username: str | None = None,
        oauth_token: str | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.channel = channel.strip().lstrip("#").lower()
        self.on_message = on_message
        self.on_status = on_status or (lambda _msg: None)
        self.bot_username = (bot_username or "").strip().lstrip("@").lower()
        self.oauth_token = normalize_oauth(oauth_token or "")
        # Authenticated only when we have BOTH a username and a token.
        self.want_auth = bool(self.oauth_token and self.bot_username)
        self.authenticated = self.want_auth  # may drop to False if login fails

        self._sock: ssl.SSLSocket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = False  # true only after Twitch's 001 welcome
        self._auth_failed = False

        if self.oauth_token and not self.bot_username:
            self.on_status(
                "Twitch: an OAuth token was given but no bot username — set the bot "
                "username too, or leave both blank for anonymous read-only."
            )

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

        # Request tags/commands/membership so we get NOTICE/RECONNECT + tags.
        self._raw("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership")

        use_auth = self.want_auth and not self._auth_failed
        if use_auth:
            self._raw(f"PASS {self.oauth_token}")
            self._raw(f"NICK {self.bot_username}")
            self.authenticated = True
            self.on_status(f"Twitch: logging in as {self.bot_username}...")
        else:
            # Anonymous read-only login (random justinfan nick).
            anon = f"justinfan{random.randint(10000, 99999)}"
            self._raw(f"NICK {anon}")
            self.authenticated = False
            self.on_status(f"Twitch: connecting to #{self.channel} (anonymous read-only)...")
        # NOTE: we mark _connected only when Twitch confirms with 001 (welcome).

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
                self.on_status(f"Twitch disconnected ({exc}). Reconnecting...")
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

        # Twitch confirms a successful login with numeric 001 (welcome).
        if " 001 " in line:
            self._connected = True
            self.on_status(
                f"Twitch: connected to #{self.channel} "
                f"({'authenticated' if self.authenticated else 'read-only'})."
            )
            return

        # Twitch tells us to reconnect.
        if line.startswith("RECONNECT") or " RECONNECT " in line:
            raise ConnectionError("server asked to reconnect")

        # Login / auth failures arrive as a NOTICE before the socket closes.
        if "NOTICE" in line and ":" in line:
            notice = line.rsplit(":", 1)[-1].strip()
            low = notice.lower()
            if "authentication failed" in low or "improperly formatted auth" in low or "login unsuccessful" in low:
                if self.want_auth and not self._auth_failed:
                    self._auth_failed = True
                    self.on_status(
                        f"Twitch login failed ({notice}). Falling back to anonymous "
                        "read-only — fix the bot username/OAuth token to post in chat."
                    )
                    raise ConnectionError("auth failed -> anonymous")
                self.on_status(f"Twitch notice: {notice}")
            return

        match = _PRIVMSG_RE.match(line)
        if not match:
            return
        nick = match.group("nick")
        message = match.group("msg").strip()
        roles = roles_from_tags(match.group("tags"))
        if nick and message:
            try:
                self.on_message(nick, message, roles)
            except Exception:
                pass
