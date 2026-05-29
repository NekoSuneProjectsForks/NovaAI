"""Screen capture + optional vision captioning for the universal game driver.

Captures the screen (mss or PIL), optionally downscales it, and asks a
multimodal model for a compact scene description so the text LLM brain can
decide actions. All deps are optional/lazy; if vision isn't configured the
driver still runs with a minimal observation.
"""
from __future__ import annotations

import base64
import io
from typing import Any

import requests

from ..config import Config


def capture_png(max_width: int = 768) -> bytes | None:
    """Grab the primary screen as PNG bytes, downscaled to max_width."""
    img = None
    try:
        import mss  # type: ignore
        from PIL import Image  # type: ignore

        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        try:
            from PIL import ImageGrab  # type: ignore

            img = ImageGrab.grab()
        except Exception:
            return None

    try:
        if img.width > max_width:
            ratio = max_width / float(img.width)
            img = img.resize((max_width, int(img.height * ratio)))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def screen_size() -> tuple[int, int] | None:
    try:
        from PIL import ImageGrab  # type: ignore

        img = ImageGrab.grab()
        return img.size
    except Exception:
        return None


def caption(config: Config, png_bytes: bytes, prompt: str) -> str:
    """Describe a screenshot via the configured vision model. Best-effort."""
    model = config.vision_model
    if not model or not png_bytes:
        return "(no vision model configured — playing without screen analysis)"
    b64 = base64.b64encode(png_bytes).decode("ascii")
    base = config.llm_api_url
    headers = {"Content-Type": "application/json"}
    if config.llm_api_key:
        headers["Authorization"] = f"Bearer {config.llm_api_key}"
    try:
        if config.llm_provider == "ollama":
            url = base.split("/api/")[0].rstrip("/") + "/api/chat"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt, "images": [b64]}],
                "stream": False,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        # OpenAI-compatible vision
        url = base
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"(vision model unavailable: {exc})"
