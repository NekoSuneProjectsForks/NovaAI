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

import re
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


class LocalSingingEngine:
    """Fully local 'sing-along': fetch timed lyrics (LRCLIB) and have NovaAI's
    XTTS voice perform them on the song's timing, optionally mixed over a backing
    track. No cloud, no RVC, no trained model — works on a modest GPU.

    Note: XTTS isn't pitched, so this is expressive timed talk-singing (on-beat),
    not melodic singing. It's the best fully-local option.
    """

    LRC_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)")

    def __init__(self, config: Config) -> None:
        self.config = config

    def _fetch_synced_lyrics(self, query: str) -> list[tuple[float, str]] | None:
        try:
            resp = requests.get(
                "https://lrclib.net/api/search",
                params={"q": query},
                headers={"User-Agent": "NovaAI"},
                timeout=15,
            )
            resp.raise_for_status()
            for item in resp.json():
                synced = item.get("syncedLyrics")
                if synced:
                    return self._parse_lrc(synced)
        except Exception:
            return None
        return None

    def _parse_lrc(self, lrc: str) -> list[tuple[float, str]]:
        out: list[tuple[float, str]] = []
        for line in lrc.splitlines():
            m = self.LRC_RE.match(line.strip())
            if not m:
                continue
            text = m.group(3).strip()
            if not text:
                continue
            out.append((int(m.group(1)) * 60 + float(m.group(2)), text))
        return out

    def _render_line(self, text, model, state, sample_rate):
        import wave

        import numpy as np

        from .tts import synthesize_xtts_to_file

        tmp = AUDIO_DIR / "_sing_line.wav"
        synthesize_xtts_to_file(text, self.config, state, model, tmp)
        with wave.open(str(tmp), "rb") as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return data.astype(np.float32) / 32768.0

    def sing(self, lyrics: str, melody_ref: str | None = None) -> Path:
        import numpy as np

        from .models import SessionState
        from .tts import ensure_xtts_model, get_xtts_output_sample_rate, write_wav_audio

        if self.config.tts_provider != "xtts":
            raise SingingError("Local singing needs the XTTS voice (TTS_PROVIDER=xtts).")

        timed = self._fetch_synced_lyrics(lyrics)
        state = SessionState(voice_enabled=True, input_mode="text")
        try:
            model = ensure_xtts_model(self.config, state)
        except Exception as exc:
            raise SingingError(f"Couldn't load the XTTS voice: {exc}") from exc
        sr = get_xtts_output_sample_rate(model)

        if timed:
            rendered = [(t, self._render_line(line, model, state, sr)) for t, line in timed]
            last_t, last_audio = rendered[-1]
            total = int((last_t + len(last_audio) / sr + 1.0) * sr)
            track = np.zeros(max(total, 1), dtype=np.float32)
            for t, audio in rendered:
                start = int(t * sr)
                end = min(start + len(audio), len(track))
                track[start:end] += audio[: end - start]
        else:
            # No synced lyrics found — sing the given text straight through.
            track = self._render_line(lyrics, model, state, sr)

        track = self._mix_backing(track, sr, melody_ref)
        np.clip(track, -1.0, 1.0, out=track)
        output = AUDIO_DIR / "song.wav"
        return write_wav_audio(output, [track], sr)

    def _mix_backing(self, vocal, sr, melody_ref):
        import numpy as np

        if not melody_ref:
            return vocal
        path = Path(melody_ref)
        if not path.is_absolute():
            from .paths import ROOT_DIR

            path = ROOT_DIR / melody_ref
        if not path.exists():
            return vocal
        try:
            import torchaudio  # decodes mp3/wav/flac

            wav, bt_sr = torchaudio.load(str(path))
            mono = wav.mean(dim=0).numpy().astype(np.float32)
            if bt_sr != sr:  # linear resample to the vocal rate
                idx = np.linspace(0, len(mono) - 1, int(len(mono) * sr / bt_sr))
                mono = np.interp(idx, np.arange(len(mono)), mono).astype(np.float32)
            length = max(len(vocal), len(mono))
            out = np.zeros(length, dtype=np.float32)
            out[: len(mono)] += mono * 0.5            # backing quieter
            out[: len(vocal)] += vocal * 0.95         # vocal on top
            return out
        except Exception:
            return vocal


def make_singing_engine(config: Config) -> SingingEngine:
    """Choose a backend, falling back to cloud when local RVC isn't viable."""
    backend = config.singing_backend
    if backend == "local":
        return LocalSingingEngine(config)
    if backend == "cloud":
        return CloudSingingEngine(config)

    # backend == "rvc": use it if hardware + config look viable, else fall back.
    vram = _vram_gb()
    too_small = vram is not None and 0 < vram < 4.0
    if too_small or not config.rvc_model_path:
        if config.singing_api_url:
            return CloudSingingEngine(config)
    return RvcSingingEngine(config)
