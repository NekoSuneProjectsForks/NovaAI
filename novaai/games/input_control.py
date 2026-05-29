"""Keyboard / mouse simulation for the universal game driver.

Uses pydirectinput when available (sends scancodes, which most games accept),
falling back to pyautogui. Both are optional, lazy-imported deps so the rest of
NovaAI runs without them. All actions are best-effort and never raise.
"""
from __future__ import annotations

import time
from typing import Any

_backend: Any = None
_backend_name = ""


def _get_backend() -> tuple[Any, str]:
    global _backend, _backend_name
    if _backend is not None:
        return _backend, _backend_name
    try:
        import pydirectinput  # type: ignore

        pydirectinput.FAILSAFE = False
        _backend = pydirectinput
        _backend_name = "pydirectinput"
        return _backend, _backend_name
    except Exception:
        pass
    try:
        import pyautogui  # type: ignore

        pyautogui.FAILSAFE = False
        _backend = pyautogui
        _backend_name = "pyautogui"
        return _backend, _backend_name
    except Exception:
        pass
    _backend = False  # mark as tried-and-failed
    _backend_name = ""
    return _backend, _backend_name


def available() -> bool:
    backend, _ = _get_backend()
    return bool(backend)


def press_key(key: str) -> str:
    backend, _ = _get_backend()
    if not backend:
        return "no input backend"
    try:
        backend.press(str(key))
        return f"pressed {key}"
    except Exception as exc:
        return f"press failed: {exc}"


def hold_key(key: str, seconds: float = 0.5) -> str:
    backend, _ = _get_backend()
    if not backend:
        return "no input backend"
    seconds = max(0.0, min(5.0, float(seconds)))
    try:
        backend.keyDown(str(key))
        time.sleep(seconds)
        backend.keyUp(str(key))
        return f"held {key} for {seconds}s"
    except Exception as exc:
        return f"hold failed: {exc}"


def move_mouse(x: int | None = None, y: int | None = None, dx: int = 0, dy: int = 0) -> str:
    backend, _ = _get_backend()
    if not backend:
        return "no input backend"
    try:
        if x is not None and y is not None:
            backend.moveTo(int(x), int(y))
            return f"moved to {x},{y}"
        backend.moveRel(int(dx), int(dy))
        return f"moved by {dx},{dy}"
    except Exception as exc:
        return f"move failed: {exc}"


def click(button: str = "left") -> str:
    backend, _ = _get_backend()
    if not backend:
        return "no input backend"
    try:
        backend.click(button=button if button in ("left", "right", "middle") else "left")
        return f"{button} click"
    except Exception as exc:
        return f"click failed: {exc}"
