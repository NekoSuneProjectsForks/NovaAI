"""NovaAI - unified stream-event model + reactions.

A single ``StreamEvent`` type that every alert source (Streamlabs, StreamElements,
Twitch EventSub, or a generic webhook from Tangia / sound-alerts / any bot) is
normalized into. The webgui dispatcher turns each event into an avatar
expression + a cute, profile-flavored spoken message, and feeds the tips total
("stockings") earnings tracker.

This module is pure/standalone (no I/O) so it is easy to unit-test; the live
socket clients live in ``stream_sources.py`` and the dispatch in ``webgui.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Canonical event types NovaAI understands.
EVENT_TYPES = {
    "donation", "follow", "subscription", "resub", "giftsub",
    "cheer", "raid", "host", "custom",
}

# Default avatar expression per event (overridable per profile).
EVENT_EXPRESSION = {
    "donation": "love",
    "follow": "happy",
    "subscription": "excited",
    "resub": "happy",
    "giftsub": "love",
    "cheer": "excited",
    "raid": "surprised",
    "host": "surprised",
    "custom": "happy",
}

# Built-in fallback messages if a profile leaves one blank.
DEFAULT_MESSAGES = {
    "donation": "Thank you so much {user} for the {amount} {currency}! You're amazing~",
    "follow": "Welcome in, {user}! Thanks for the follow~",
    "subscription": "{user} just subscribed! Thank you so much!",
    "resub": "{user} resubbed for {months} months! Thank you~",
    "giftsub": "{user} gifted subs! So generous, thank you~",
    "cheer": "Thanks for the {amount} bits, {user}!",
    "raid": "Raid! Welcome everyone from {user}'s channel!",
    "host": "Thanks for the host, {user}!",
    "custom": "Thank you {user}!",
}

# Events whose amount adds to the tips/earnings ("stockings") tally.
EARNING_EVENTS = {"donation", "cheer"}


@dataclass
class StreamEvent:
    type: str
    user: str = "someone"
    amount: float = 0.0
    currency: str = "USD"
    months: int = 0
    tier: str = ""
    viewers: int = 0
    message: str = ""
    source: str = ""          # streamlabs | streamelements | twitch | webhook | manual
    raw: dict[str, Any] = field(default_factory=dict)

    def expression(self, overrides: dict[str, str] | None = None) -> str:
        if overrides:
            custom = str(overrides.get(self.type, "")).strip()
            if custom:
                return custom
        return EVENT_EXPRESSION.get(self.type, "happy")


def _to_float(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _fmt_amount(amount: float) -> str:
    """Drop the trailing .00 so '$5' reads nicer than '$5.0'."""
    if amount == int(amount):
        return str(int(amount))
    return f"{amount:.2f}"


def build_message(event: StreamEvent, templates: dict[str, str] | None = None) -> str:
    """Fill the profile's template (or a default) with the event's fields."""
    templates = templates or {}
    template = str(templates.get(event.type, "")).strip() or DEFAULT_MESSAGES.get(
        event.type, DEFAULT_MESSAGES["custom"]
    )
    fields = {
        "user": event.user or "someone",
        "amount": _fmt_amount(event.amount),
        "currency": event.currency or "",
        "months": event.months or 1,
        "tier": event.tier or "",
        "viewers": event.viewers or 0,
        "message": event.message or "",
    }

    class _Safe(dict):
        def __missing__(self, key: str) -> str:  # tolerate unknown placeholders
            return ""

    try:
        return template.format_map(_Safe(fields)).strip()
    except Exception:
        return DEFAULT_MESSAGES.get(event.type, "Thank you!")


# ── Normalizers: platform payload -> StreamEvent(s) ─────────────────────────


def from_generic(payload: dict[str, Any]) -> StreamEvent | None:
    """A simple ``{type, user, amount, currency, months, message}`` shape.

    This is what the webhook accepts, so Twitch EventSub forwarders, Tangia,
    sound-alert tools, or any custom bot can post events without us hard-coding
    each one's schema.
    """
    if not isinstance(payload, dict):
        return None
    etype = str(payload.get("type") or payload.get("event") or "").strip().lower()
    alias = {
        "tip": "donation", "donate": "donation", "bits": "cheer", "bit": "cheer",
        "sub": "subscription", "subscribe": "subscription",
        "resubscription": "resub", "gift": "giftsub", "subgift": "giftsub",
        "communitygiftpurchase": "giftsub", "raided": "raid",
    }
    etype = alias.get(etype, etype)
    if etype not in EVENT_TYPES:
        return None
    return StreamEvent(
        type=etype,
        user=str(payload.get("user") or payload.get("name") or payload.get("from") or "someone"),
        amount=_to_float(payload.get("amount") or payload.get("bits") or 0),
        currency=str(payload.get("currency") or "USD"),
        months=_to_int(payload.get("months") or payload.get("streak") or 0),
        tier=str(payload.get("tier") or ""),
        viewers=_to_int(payload.get("viewers") or payload.get("raiders") or 0),
        message=str(payload.get("message") or ""),
        source=str(payload.get("source") or "webhook"),
        raw=payload,
    )


def from_streamlabs(message: dict[str, Any]) -> list[StreamEvent]:
    """Streamlabs socket 'event' payload: {type, message:[{...}]}."""
    out: list[StreamEvent] = []
    if not isinstance(message, dict):
        return out
    etype = str(message.get("type") or "").strip().lower()
    alias = {
        "donation": "donation", "follow": "follow", "subscription": "subscription",
        "resub": "resub", "subMysteryGift": "giftsub", "bits": "cheer",
        "host": "host", "raid": "raid",
    }
    etype = alias.get(etype, etype)
    if etype not in EVENT_TYPES:
        return out
    items = message.get("message")
    if not isinstance(items, list):
        items = [items] if isinstance(items, dict) else []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append(StreamEvent(
            type=etype,
            user=str(it.get("name") or it.get("from") or "someone"),
            amount=_to_float(it.get("amount") or 0),
            currency=str(it.get("currency") or "USD"),
            months=_to_int(it.get("months") or 0),
            viewers=_to_int(it.get("raiders") or it.get("viewers") or 0),
            message=str(it.get("message") or ""),
            source="streamlabs",
            raw=it,
        ))
    return out


def from_streamelements(payload: dict[str, Any]) -> StreamEvent | None:
    """StreamElements 'event'/'event:test' payload: {type, data:{...}}."""
    if not isinstance(payload, dict):
        return None
    etype = str(payload.get("type") or "").strip().lower()
    alias = {
        "tip": "donation", "cheer": "cheer", "follow": "follow",
        "subscriber": "subscription", "resub": "resub",
        "communityGiftPurchase": "giftsub", "subgift": "giftsub",
        "raid": "raid", "host": "host",
    }
    etype = alias.get(etype, etype)
    if etype not in EVENT_TYPES:
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return StreamEvent(
        type=etype,
        user=str(data.get("username") or data.get("displayName") or data.get("name") or "someone"),
        amount=_to_float(data.get("amount") or 0),
        currency=str(data.get("currency") or "USD"),
        months=_to_int(data.get("amount") if etype == "resub" else data.get("months") or 0),
        tier=str(data.get("tier") or ""),
        viewers=_to_int(data.get("amount") if etype in {"raid", "host"} else 0),
        message=str(data.get("message") or ""),
        source="streamelements",
        raw=data,
    )


def from_twitch_eventsub(payload: dict[str, Any]) -> StreamEvent | None:
    """Twitch EventSub notification: {subscription:{type}, event:{...}}."""
    if not isinstance(payload, dict):
        return None
    sub = payload.get("subscription") if isinstance(payload.get("subscription"), dict) else {}
    ev = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    sub_type = str(sub.get("type") or "").strip().lower()
    mapping = {
        "channel.follow": "follow",
        "channel.subscribe": "subscription",
        "channel.subscription.message": "resub",
        "channel.subscription.gift": "giftsub",
        "channel.cheer": "cheer",
        "channel.raid": "raid",
    }
    etype = mapping.get(sub_type)
    if not etype:
        return None
    user = (
        ev.get("user_name") or ev.get("user_login")
        or ev.get("from_broadcaster_user_name") or "someone"
    )
    return StreamEvent(
        type=etype,
        user=str(user),
        amount=_to_float(ev.get("bits") or 0),
        months=_to_int(ev.get("cumulative_months") or ev.get("total") or 0),
        tier=str(ev.get("tier") or ""),
        viewers=_to_int(ev.get("viewers") or 0),
        message=str((ev.get("message") or {}).get("text", "") if isinstance(ev.get("message"), dict) else ev.get("message") or ""),
        source="twitch",
        raw=ev,
    )
