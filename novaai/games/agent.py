"""GameAgent - the game-agnostic LLM control loop.

Each tick it observes the world, asks the LLM (via the shared engine) for a
short first-person thought plus one high-level command as JSON, narrates the
thought (so it appears in chat / TTS / avatar / stream), executes the command
through the driver, and feeds the outcome back in. Runs on a daemon thread and
never crashes the app.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable

from ..config import Config
from ..engine import GenerationRequest, detect_emotion, generate_reply
from .base import GameCommand, GameDriver

# Verbs that need a subject (item/block) in their args.
_NAME_VERBS = {
    "mine", "collect", "gather", "bring", "store", "deposit", "find_in_chests",
    "withdraw", "drop", "craft", "place", "place_at", "smelt", "cook", "equip",
    "plant", "plant_tree",
}
# Map everyday words in a goal to a concrete Minecraft name the bridge can find.
_SUBJECT_ALIASES = {
    "wood": "oak_log", "wooden": "oak_log", "logs": "log", "log": "log", "timber": "log",
    "plank": "planks", "stick": "stick", "cobble": "cobblestone", "cobblestone": "cobblestone",
    "stone": "stone", "diamond": "diamond", "iron": "iron", "gold": "gold",
    "coal": "coal", "redstone": "redstone", "copper": "copper", "lapis": "lapis",
    "emerald": "emerald", "dirt": "dirt", "sand": "sand", "gravel": "gravel",
    "wheat": "wheat", "carrot": "carrot", "potato": "potato", "food": "beef",
    "wool": "wool", "glass": "glass", "water": "water", "bucket": "bucket",
    "pickaxe": "pickaxe", "axe": "axe", "sword": "sword", "shovel": "shovel",
    "armor": "armor", "torch": "torch", "bed": "bed",
}


def _infer_subject(goal: str) -> str | None:
    g = f" {(goal or '').lower()} "
    for word, mapped in _SUBJECT_ALIASES.items():
        if f"{word}" in g:
            return mapped
    return None


def _extract_command(reply: str) -> dict[str, Any] | None:
    """Best-effort parse of the model's JSON action (tolerant of fences/prose)."""
    if not reply:
        return None
    text = reply.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip().strip("`").strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start:i + 1]
                for attempt in (blob, blob.replace("'", '"')):
                    try:
                        data = json.loads(attempt)
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass
                break
    return None


class GameAgent:
    def __init__(
        self,
        driver: GameDriver,
        config: Config,
        profile_getter: Callable[[], dict[str, Any]],
        narrate: Callable[[str, str], None],
        on_update: Callable[[dict[str, Any]], None] | None = None,
        remember: Callable[[str], None] | None = None,
        tick_seconds: float = 4.0,
        goal: str = "explore and survive",
    ) -> None:
        self.driver = driver
        self.config = config
        self.profile_getter = profile_getter
        self.narrate = narrate
        self.on_update = on_update or (lambda _state: None)
        self.remember = remember or (lambda _text: None)
        self.tick_seconds = max(1.0, tick_seconds)
        self.goal = goal

        self._stop = threading.Event()
        self._wake = threading.Event()  # fire a tick immediately (e.g. new order)
        self._thread: threading.Thread | None = None
        self._log: list[dict[str, str]] = []  # short rolling game history

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="NovaAIGameAgent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        # Abort any in-flight action immediately (e.g. a long pathfinder move):
        # stopping the driver makes the current observe/act call fail fast so the
        # loop unwinds instead of blocking until the action finishes.
        try:
            self.driver.stop()
        except Exception:
            pass

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def set_goal(self, goal: str) -> None:
        self.goal = goal.strip() or self.goal
        self._wake.set()  # act on the new order right away

    # ── loop ──────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            self.driver.start()
        except Exception as exc:
            self.narrate(f"I couldn't start the game: {exc}", "anxious")
            return
        self.narrate(f"Alright, let's play. Goal: {self.goal}.", "happy")

        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                self.narrate(f"Something went wrong: {exc}", "anxious")
            # Wait for the next tick, but wake instantly on a new order / stop.
            self._wake.wait(self.tick_seconds)
            self._wake.clear()

        try:
            self.driver.stop()
        except Exception:
            pass
        self.narrate("Okay, I'm done playing for now.", "neutral")

    def _tick(self) -> None:
        if self._stop.is_set():
            return
        obs = self.driver.observe()
        try:
            self.on_update(obs.raw)
        except Exception:
            pass
        if self._stop.is_set():
            return

        verbs = self.driver.available_verbs()

        def _driver_text(method: str) -> str:
            if hasattr(self.driver, method):
                try:
                    return self.driver.__getattribute__(method)() or ""
                except Exception:
                    return ""
            return ""

        mission = _driver_text("mission")
        verbs_help = _driver_text("verbs_help")
        framing = (
            f"You are autonomously playing {self.driver.name}. Think out loud briefly in "
            "first person, then choose ONE action. Respond ONLY with JSON of the form "
            '{"thought": "<one or two in-character sentences>", "verb": "<one verb>", '
            '"args": {<key: value>}}. '
            + (f"\n{mission}" if mission else "")
            + f"\nAllowed verbs: {', '.join(verbs)}."
            + (f"\n{verbs_help}" if verbs_help else "")
        )
        user_prompt = (
            f"Goal: {self.goal}\n\nCurrent world state:\n{obs.text}\n\n"
            "Decide your next single action now."
        )

        result = generate_reply(
            GenerationRequest(
                user_text=user_prompt,
                profile=self.profile_getter(),
                config=self.config,
                source="game",
                extra_system=[framing],
                use_shared_history=False,
                history=list(self._log),
                # Game replies are short JSON; cap tokens so local models (Ollama)
                # respond fast and don't time out each tick.
                max_tokens=256,
            )
        )

        if self._stop.is_set():
            return

        command = _extract_command(result.reply)
        thought = str(command.get("thought", "")).strip() if command else ""
        verb = str(command.get("verb", "")).strip().lower() if command else ""
        args = (command.get("args") if command and isinstance(command.get("args"), dict) else {})

        if thought:
            self.narrate(thought, detect_emotion(thought))
            self.remember(f"While playing {self.driver.name}: {thought}")
        elif command is None:
            # Model didn't give a usable action — show a snippet so it's visible.
            snippet = result.reply.strip().replace("\n", " ")[:160]
            if snippet:
                self.narrate(snippet, result.emotion)

        # Fall back to wandering so the bot always does *something* (and so a
        # broken pathfinder/version doesn't leave it frozen).
        if not verb or verb not in verbs:
            verb, args = ("wander", {"seconds": 2}) if "wander" in verbs else ("look", {})

        # If a subject-needing verb came with no item/block, infer it from the
        # goal so "I need wood" -> mine {name: oak_log} instead of failing.
        if verb in _NAME_VERBS and not any(
            args.get(k) for k in ("name", "item", "block", "seed", "sapling", "input")
        ):
            subject = _infer_subject(self.goal)
            if subject:
                args = {**args, "name": subject}

        outcome = self.driver.act(GameCommand(verb=verb, args=args))
        outcome_text = str(outcome.get("message", outcome))
        # Surface failures so the user can see why nothing's happening.
        if isinstance(outcome, dict) and outcome.get("ok") is False:
            self.narrate(f"({verb}: {outcome_text})", "anxious")

        self._log.append({"role": "assistant", "content": thought or f"{verb} {args}"})
        self._log.append({"role": "user", "content": f"Result: {outcome_text}"})
        if len(self._log) > 12:
            self._log = self._log[-12:]
