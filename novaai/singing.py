"""NovaAI - singing engine (Neuro-sama style).

Turns lyrics (optionally guided by a melody/vocal reference) into a sung audio
clip that plays through the normal audio path, so the avatar lip-syncs to it for
free (via the Phase 2 amplitude seam).

Two interchangeable backends behind one interface:
  * CloudSingingEngine - calls a hosted singing/voice API. Safe default and the
    realistic choice on a modest GPU.
  * RvcSingingEngine   - local RVC voice-conversion over a melody/vocal reference.
    Heavier; deps are optional and lazy-imported.

The factory falls back to cloud when local RVC is unavailable or VRAM is low.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import requests

from .config import Config
from .paths import AUDIO_DIR


class SingingError(RuntimeError):
    pass


class SingingEngine(Protocol):
    def sing(self, lyrics: str, melody_ref: str | None = None) -> Path:
        ...


def _vram_gb() -> float | None:
    try:
        import torch

        if not torch.cuda.is_available():
            return 0.0
        return torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    except Exception:
        return None


class CloudSingingEngine:
    def __init__(self, config: Config) -> None:
        self.config = config

    def sing(self, lyrics: str, melody_ref: str | None = None) -> Path:
        url = self.config.singing_api_url
        if not url:
            raise SingingError(
                "No singing API configured. Set SINGING_API_URL (and SINGING_API_KEY) in .env."
            )
        headers = {"Content-Type": "application/json"}
        if self.config.singing_api_key:
            headers["Authorization"] = f"Bearer {self.config.singing_api_key}"
        payload = {"lyrics": lyrics}
        if melody_ref:
            payload["melody_ref"] = melody_ref
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SingingError(f"Singing API request failed: {exc}") from exc

        content_type = resp.headers.get("Content-Type", "")
        output = AUDIO_DIR / "song.wav"
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        if "application/json" in content_type:
            # Expect a URL to the rendered audio.
            data = resp.json()
            audio_url = data.get("url") or data.get("audio_url")
            if not audio_url:
                raise SingingError("Singing API returned JSON without an audio URL.")
            audio = requests.get(audio_url, timeout=120)
            audio.raise_for_status()
            output.write_bytes(audio.content)
        else:
            output.write_bytes(resp.content)
        return output


class RvcSingingEngine:
    """Local RVC voice-conversion. Requires a melody/vocal reference to convert."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def sing(self, lyrics: str, melody_ref: str | None = None) -> Path:
        if not melody_ref:
            raise SingingError(
                "Local RVC singing needs a melody/vocal reference (a .wav of the song's "
                "vocals or an acapella) to convert into NovaAI's voice. Provide melody_ref, "
                "or switch SINGING_BACKEND=cloud."
            )
        ref_path = Path(melody_ref)
        if not ref_path.is_absolute():
            from .paths import ROOT_DIR

            ref_path = ROOT_DIR / melody_ref
        if not ref_path.exists():
            raise SingingError(f"Melody reference not found: {ref_path}")
        if not self.config.rvc_model_path:
            raise SingingError("Set RVC_MODEL_PATH in .env to your trained RVC model (.pth).")

        try:
            # Lazy import - RVC packaging is platform-sensitive and optional.
            from rvc_python.infer import RVCInference  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dep
            raise SingingError(
                "RVC is not installed. Install an RVC inference package (e.g. rvc-python) "
                "or use SINGING_BACKEND=cloud."
            ) from exc

        output = AUDIO_DIR / "song.wav"
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        try:
            rvc = RVCInference(model_path=self.config.rvc_model_path)
            rvc.infer_file(str(ref_path), str(output))
        except Exception as exc:
            raise SingingError(f"RVC inference failed: {exc}") from exc
        return output


def make_singing_engine(config: Config) -> SingingEngine:
    """Choose a backend, falling back to cloud when local RVC isn't viable."""
    backend = config.singing_backend
    if backend == "cloud":
        return CloudSingingEngine(config)

    # backend == "rvc": use it if hardware + config look viable, else fall back.
    vram = _vram_gb()
    too_small = vram is not None and 0 < vram < 4.0
    if too_small or not config.rvc_model_path:
        if config.singing_api_url:
            return CloudSingingEngine(config)
    return RvcSingingEngine(config)
