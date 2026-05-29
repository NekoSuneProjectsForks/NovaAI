"""Minecraft driver via a Node/Mineflayer bridge.

Mineflayer is a Node.js library, so the actual bot lives in a small Node process
(``node/minecraft-bridge/bridge.js``) that exposes a local HTTP API. This Python
driver launches that process and talks to it over HTTP, keeping the LLM brain in
``GameAgent`` and only the low-level execution in Node.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from ..config import Config
from ..paths import ROOT_DIR
from .base import GameCommand, GameObservation

BRIDGE_DIR = ROOT_DIR / "node" / "minecraft-bridge"

_VERBS = ["goto", "mine", "collect", "craft", "place", "say", "look", "wait", "stop"]


class MinecraftDriver:
    name = "Minecraft"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.bridge_port = config.mc_bridge_port
        self.base_url = f"http://127.0.0.1:{self.bridge_port}"
        self._proc: subprocess.Popen | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        node = self.config.node_path or shutil.which("node")
        if not node:
            raise RuntimeError(
                "Node.js was not found. Install Node 18+ and/or set NODE_PATH in .env."
            )
        bridge_js = BRIDGE_DIR / "bridge.js"
        if not bridge_js.exists():
            raise RuntimeError(f"Minecraft bridge not found at {bridge_js}.")
        if not (BRIDGE_DIR / "node_modules").exists():
            raise RuntimeError(
                "Minecraft bridge dependencies are not installed. Run "
                f"'npm install' in {BRIDGE_DIR}."
            )

        env_args = [
            node,
            str(bridge_js),
            "--host", str(self.config.mc_host),
            "--port", str(self.config.mc_port),
            "--username", str(self.config.mc_username),
            "--bridge-port", str(self.bridge_port),
            "--auth", str(self.config.mc_auth),
        ]
        self._proc = subprocess.Popen(
            env_args,
            cwd=str(BRIDGE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait for the bridge to come up.
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError("The Minecraft bridge process exited during startup.")
            try:
                resp = requests.get(self.base_url + "/health", timeout=2)
                if resp.ok:
                    return
            except requests.RequestException:
                pass
            time.sleep(1.0)
        raise RuntimeError("Timed out waiting for the Minecraft bridge to connect.")

    def stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            except Exception:
                pass
        self._proc = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ── observe / act ───────────────────────────────────────────────────────────

    def observe(self) -> GameObservation:
        try:
            resp = requests.get(self.base_url + "/observe", timeout=5)
            raw = resp.json() if resp.ok else {}
        except requests.RequestException:
            raw = {}
        return GameObservation(raw=raw, text=self._format(raw))

    def describe_state(self) -> str:
        return self.observe().text

    def act(self, command: GameCommand) -> dict[str, Any]:
        try:
            resp = requests.post(
                self.base_url + "/act",
                json={"verb": command.verb, "args": command.args},
                timeout=self.config.game_tick_seconds + 20,
            )
            if resp.ok:
                return resp.json()
            return {"ok": False, "message": f"bridge HTTP {resp.status_code}"}
        except requests.RequestException as exc:
            return {"ok": False, "message": f"bridge unreachable: {exc}"}

    def available_verbs(self) -> list[str]:
        return list(_VERBS)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _format(raw: dict[str, Any]) -> str:
        if not raw:
            return "No world data yet (bridge connecting)."
        pos = raw.get("position", {})
        inv = raw.get("inventory", [])
        nearby = raw.get("nearbyBlocks", [])
        entities = raw.get("nearbyEntities", [])
        inv_text = ", ".join(f"{i.get('name')} x{i.get('count')}" for i in inv[:12]) or "empty"
        lines = [
            f"Health: {raw.get('health', '?')}/20, Food: {raw.get('food', '?')}/20",
            f"Position: x={pos.get('x','?')} y={pos.get('y','?')} z={pos.get('z','?')}",
            f"Time: {raw.get('timeOfDay', '?')}",
            f"Inventory: {inv_text}",
            f"Nearby blocks: {', '.join(nearby[:12]) or 'none'}",
            f"Nearby entities: {', '.join(entities[:8]) or 'none'}",
        ]
        return "\n".join(lines)
