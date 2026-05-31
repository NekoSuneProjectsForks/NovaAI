"""VRChat driver via the official OSC API.

Uses VRChat's built-in OSC input API (enable OSC in VRChat's Action Menu) to walk
around, look, jump, type in the chatbox, and set avatar parameters/emotes. This
is the *supported*, TOS-friendly way to drive an avatar in VRChat — it does NOT
inject inputs or touch the game process, so it avoids Easy Anti-Cheat issues.

To also "see" the world, set a vision model (VISION_MODEL) and the driver will
caption the screen each observation.
"""
from __future__ import annotations

import time
from typing import Any

from ..config import Config
from . import screen
from .base import GameCommand, GameObservation

_VERBS = ["walk", "back", "turn", "jump", "say", "emote", "wait"]


class VRChatDriver:
    name = "VRChat"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._client: Any = None

    def start(self) -> None:
        try:
            from pythonosc.udp_client import SimpleUDPClient  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "python-osc is not installed. Run: pip install python-osc"
            ) from exc
        self._client = SimpleUDPClient(
            self.config.vrchat_osc_host, self.config.vrchat_osc_port
        )

    def stop(self) -> None:
        self._client = None

    def is_running(self) -> bool:
        return self._client is not None

    def observe(self) -> GameObservation:
        if self.config.vision_model:
            png = screen.capture_png()
            if png is not None:
                text = screen.caption(
                    self.config,
                    png,
                    "You are the eyes of an AI in VRChat. Describe what's on screen: "
                    "the room/world, nearby players or avatars, menus, and anything "
                    "interesting to walk toward. Be concise.",
                )
                return GameObservation(raw={"scene": text}, text=text)
        return GameObservation(
            raw={},
            text="In VRChat (OSC control). No vision model set, so I can't see the world; "
            "I can still walk, turn, jump, emote, and chat.",
        )

    def describe_state(self) -> str:
        return self.observe().text

    def _send(self, address: str, value: Any) -> None:
        if self._client is not None:
            self._client.send_message(address, value)

    def _timed_axis(self, address: str, value: float, seconds: float) -> None:
        seconds = max(0.0, min(6.0, float(seconds)))
        self._send(address, float(value))
        time.sleep(seconds)
        self._send(address, 0.0)

    def act(self, command: GameCommand) -> dict[str, Any]:
        if self._client is None:
            return {"ok": False, "message": "not connected"}
        verb = command.verb
        args = command.args or {}
        try:
            if verb == "walk":
                self._timed_axis("/input/Vertical", 1.0, args.get("seconds", 1.5))
                return {"ok": True, "message": "walked forward"}
            if verb == "back":
                self._timed_axis("/input/Vertical", -1.0, args.get("seconds", 1.0))
                return {"ok": True, "message": "walked back"}
            if verb == "turn":
                direction = 1.0 if str(args.get("direction", "right")).lower() == "right" else -1.0
                self._timed_axis("/input/LookHorizontal", direction, args.get("seconds", 0.6))
                return {"ok": True, "message": f"turned {args.get('direction','right')}"}
            if verb == "jump":
                self._send("/input/Jump", 1)
                time.sleep(0.15)
                self._send("/input/Jump", 0)
                return {"ok": True, "message": "jumped"}
            if verb == "say":
                text = str(args.get("text", ""))[:140]
                # /chatbox/input: string, post-immediately(bool), notify(bool)
                self._send("/chatbox/input", [text, True, False])
                return {"ok": True, "message": "sent to chatbox"}
            if verb == "emote":
                name = str(args.get("param", "")).strip()
                if not name:
                    return {"ok": False, "message": "emote needs a param name"}
                self._send(f"/avatar/parameters/{name}", args.get("value", 1))
                return {"ok": True, "message": f"set {name}"}
            if verb == "wait":
                return {"ok": True, "message": "waited"}
            return {"ok": False, "message": f"unknown verb {verb}"}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def available_verbs(self) -> list[str]:
        return list(_VERBS)

    def default_goal(self) -> str:
        return "Hang out in VRChat: wander around, look at people/places, and chat with players."

    def mission(self) -> str:
        return (
            "You are an avatar in VRChat (controlled via OSC). Do NOT use Minecraft "
            "commands (no !mine/!searchForBlock/etc.) — they do nothing here. Move "
            "around, look, and chat naturally with people. One action per turn."
        )

    def verbs_help(self) -> str:
        return (
            "Args go in args.\n"
            "walk{seconds?} = walk forward | back{seconds?} = step back | "
            "turn{direction:'left'|'right',seconds?} = turn | jump = jump | "
            "say{text} = talk in the chatbox | emote{param,value?} = avatar "
            "expression | wait = idle this turn."
        )
