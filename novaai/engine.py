"""NovaAI - shared response-generation engine.

A single place that turns an input (from chat, Twitch, or a game agent) into a
reply, regardless of source. It orchestrates the LLM call in ``chat.py`` plus
lightweight emotion/danger tagging used to drive the avatar.

It deliberately performs **no** side effects: it does not append history, push
to the frontend, or speak. Callers own those concerns so each source (chat,
stream, game) can react differently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .chat import request_reply
from .config import Config


@dataclass
class GenerationRequest:
    user_text: str
    profile: dict[str, Any]
    config: Config
    source: str = "chat"  # "chat" | "twitch" | "game"
    web_context: str | None = None
    extra_system: list[str] = field(default_factory=list)
    use_shared_history: bool = True
    history: list[dict[str, str]] | None = None
    speaker_label: str | None = None


@dataclass
class GenerationResult:
    reply: str
    emotion: str
    danger: bool


_SAD_WORDS = ("sad", "upset", "hurt", "depressed", "annoyed", "lonely", "cry")
_HAPPY_WORDS = ("happy", "joy", "love", "excited", "awesome", "great", "lol", "haha")
_ANXIOUS_WORDS = ("scared", "afraid", "nervous", "worried", "anxious")
_ANGRY_WORDS = ("angry", "mad", "furious", "irritated", "rage")
_DANGER_WORDS = (
    "danger",
    "fire",
    "help",
    "emergency",
    "attack",
    "threat",
    "warning",
    "alarm",
)


def detect_emotion(text: str) -> str:
    """Keyword-based emotion tag matching the avatar's expression presets."""
    normalized = str(text or "").lower()
    # Order matters: check angry before sad so "angry" is not absorbed by sad.
    if any(word in normalized for word in _ANGRY_WORDS):
        return "angry"
    if any(word in normalized for word in _ANXIOUS_WORDS):
        return "anxious"
    if any(word in normalized for word in _SAD_WORDS):
        return "sad"
    if any(word in normalized for word in _HAPPY_WORDS):
        return "happy"
    return "neutral"


def detect_danger(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(keyword in normalized for keyword in _DANGER_WORDS)


def generate_reply(req: GenerationRequest) -> GenerationResult:
    """Generate a reply for any source. No side effects."""
    # When sharing the chat history, pass None so request_reply reads it itself.
    # Otherwise use the caller-provided history (an empty list means "no history").
    if req.use_shared_history:
        history = None
    else:
        history = req.history if req.history is not None else []
    reply = request_reply(
        req.user_text,
        req.profile,
        req.config,
        web_context=req.web_context,
        extra_system=req.extra_system or None,
        history=history,
        speaker_label=req.speaker_label,
    )
    combined = f"{req.user_text} {reply}"
    return GenerationResult(
        reply=reply,
        emotion=detect_emotion(combined),
        danger=detect_danger(combined),
    )
