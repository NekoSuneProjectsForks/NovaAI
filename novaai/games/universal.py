"""Universal vision + keyboard/mouse game driver.

The "any game" path: capture the screen, let a vision model describe it, and the
LLM brain chooses keyboard/mouse actions. Works for most TOS-safe single-player
games (Terraria, Unturned, Celeste, etc.). It is inherently best-effort: high
latency and not suitable for twitch-precision play.

Implements the same GameDriver contract as the Minecraft driver, so the
GameAgent brain is unchanged.
"""
from __future__ import annotations

from typing import Any

from ..config import Config
from . import input_control, screen
from .base import GameCommand, GameObservation

_VERBS = ["press", "hold", "move_mouse", "click", "say", "wait"]


class UniversalGameDriver:
    name = "a PC game"

    # A short scene-description prompt for the vision model.
    vision_prompt = (
        "You are the eyes of a game-playing AI. Describe this game screenshot in 2-3 "
        "sentences: what game/screen it looks like, the player's situation, visible "
        "menus or prompts, health/resources, and any immediate threat or objective."
    )

    def __init__(self, config: Config, game_name: str | None = None) -> None:
        self.config = config
        if game_name:
            self.name = game_name
        self._running = False

    def start(self) -> None:
        if not input_control.available():
            raise RuntimeError(
                "Input simulation is unavailable. Install it with: "
                "pip install pydirectinput mss pillow"
            )
        self._running = True

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def observe(self) -> GameObservation:
        png = screen.capture_png()
        if png is None:
            return GameObservation(raw={}, text="(could not capture the screen)")
        text = screen.caption(self.config, png, self.vision_prompt)
        size = screen.screen_size()
        raw: dict[str, Any] = {"scene": text}
        if size:
            raw["screen"] = {"width": size[0], "height": size[1]}
        return GameObservation(raw=raw, text=text)

    def describe_state(self) -> str:
        return self.observe().text

    def act(self, command: GameCommand) -> dict[str, Any]:
        verb = command.verb
        args = command.args or {}
        if verb == "press":
            return {"ok": True, "message": input_control.press_key(args.get("key", ""))}
        if verb == "hold":
            return {
                "ok": True,
                "message": input_control.hold_key(
                    args.get("key", ""), float(args.get("seconds", 0.5))
                ),
            }
        if verb == "move_mouse":
            return {
                "ok": True,
                "message": input_control.move_mouse(
                    args.get("x"), args.get("y"), int(args.get("dx", 0)), int(args.get("dy", 0))
                ),
            }
        if verb == "click":
            return {"ok": True, "message": input_control.click(args.get("button", "left"))}
        if verb in ("say", "wait"):
            return {"ok": True, "message": verb}
        return {"ok": False, "message": f"unknown verb {verb}"}

    def available_verbs(self) -> list[str]:
        return list(_VERBS)
