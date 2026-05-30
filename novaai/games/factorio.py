"""Factorio driver via the Source RCON protocol (stdlib only).

Factorio exposes an RCON console; commands prefixed with ``/silent-command`` run
Lua and can return structured data via ``rcon.print(...)``. This driver reads
game state and issues high-level actions through RCON, so no vision is needed.

Enable RCON on the server (``--rcon-port`` + ``--rcon-password``) and set
FACTORIO_RCON_* in .env.
"""
from __future__ import annotations

import socket
import struct
from typing import Any

from ..config import Config
from .base import GameCommand, GameObservation

_SERVERDATA_AUTH = 3
_SERVERDATA_EXECCOMMAND = 2

_VERBS = ["say", "run_lua", "wait"]


class _Rcon:
    def __init__(self, host: str, port: int, password: str) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.sock: socket.socket | None = None
        self._id = 0

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.sock.settimeout(10)
        self._send(_SERVERDATA_AUTH, self.password)
        _id, _type, _body = self._recv()
        if _id == -1:
            raise RuntimeError("Factorio RCON authentication failed (bad password?).")

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def command(self, body: str) -> str:
        self._send(_SERVERDATA_EXECCOMMAND, body)
        _id, _type, text = self._recv()
        return text

    def _send(self, ptype: int, body: str) -> None:
        assert self.sock is not None
        self._id += 1
        payload = struct.pack("<ii", self._id, ptype) + body.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)

    def _recv(self) -> tuple[int, int, str]:
        assert self.sock is not None
        raw_len = self._read_exact(4)
        (length,) = struct.unpack("<i", raw_len)
        data = self._read_exact(length)
        rid, rtype = struct.unpack("<ii", data[:8])
        body = data[8:-2].decode("utf-8", errors="ignore")
        return rid, rtype, body

    def _read_exact(self, n: int) -> bytes:
        assert self.sock is not None
        chunks = b""
        while len(chunks) < n:
            part = self.sock.recv(n - len(chunks))
            if not part:
                raise ConnectionError("RCON connection closed")
            chunks += part
        return chunks


class FactorioDriver:
    name = "Factorio"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._rcon: _Rcon | None = None

    def start(self) -> None:
        if not self.config.factorio_rcon_password:
            raise RuntimeError("Set FACTORIO_RCON_PASSWORD (and port) in .env.")
        self._rcon = _Rcon(
            self.config.factorio_rcon_host,
            self.config.factorio_rcon_port,
            self.config.factorio_rcon_password,
        )
        self._rcon.connect()

    def stop(self) -> None:
        if self._rcon:
            self._rcon.close()
        self._rcon = None

    def is_running(self) -> bool:
        return self._rcon is not None and self._rcon.sock is not None

    def observe(self) -> GameObservation:
        if not self._rcon:
            return GameObservation(raw={}, text="(not connected)")
        lua = (
            "/silent-command local p=game.connected_players[1]; "
            "if p then rcon.print(game.table_to_json({"
            "name=p.name, x=math.floor(p.position.x), y=math.floor(p.position.y), "
            "health=p.character and p.character.health or 0, "
            "tick=game.tick})) else rcon.print('{}') end"
        )
        try:
            raw_text = self._rcon.command(lua)
            import json

            raw = json.loads(raw_text) if raw_text.strip().startswith("{") else {}
        except Exception as exc:
            raw = {"error": str(exc)}
        return GameObservation(raw=raw, text=self._format(raw))

    def describe_state(self) -> str:
        return self.observe().text

    def act(self, command: GameCommand) -> dict[str, Any]:
        if not self._rcon:
            return {"ok": False, "message": "not connected"}
        verb = command.verb
        args = command.args or {}
        try:
            if verb == "say":
                self._rcon.command(f"/silent-command game.print({_lua_str(args.get('text',''))})")
                return {"ok": True, "message": "announced in game"}
            if verb == "run_lua":
                code = str(args.get("lua") or args.get("code") or "")
                if not code:
                    return {"ok": False, "message": "no lua provided"}
                out = self._rcon.command("/silent-command " + code)
                return {"ok": True, "message": out or "ran lua"}
            if verb == "wait":
                return {"ok": True, "message": "waited"}
            return {"ok": False, "message": f"unknown verb {verb}"}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def available_verbs(self) -> list[str]:
        return list(_VERBS)

    @staticmethod
    def _format(raw: dict[str, Any]) -> str:
        if not raw or raw.get("error"):
            return f"(no data{': ' + raw['error'] if raw.get('error') else ''})"
        return (
            f"Player {raw.get('name','?')} at x={raw.get('x','?')} y={raw.get('y','?')}, "
            f"health={raw.get('health','?')}, tick={raw.get('tick','?')}"
        )


def _lua_str(text: str) -> str:
    escaped = str(text).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
