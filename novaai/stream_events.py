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
    platform: str = ""        # twitch | youtube | facebook | kick | trovo | streamlabs
    event_id: str = ""        # de-dupe key when the source provides one
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


# Streamlabs tags every event with the platform it came from in the top-level
# "for" field. Fold those to canonical platform names so they can be filtered.
_SL_PLATFORM = {
    "streamlabs": "streamlabs",          # the tip jar (donations)
    "twitch_account": "twitch",
    "youtube_account": "youtube",
    "facebook_account": "facebook",
    "kick_account": "kick",
    "trovo_account": "trovo",
}


def _sl_platform(message: dict[str, Any], etype: str) -> str:
    """Canonical platform name for a Streamlabs event.

    Uses the top-level ``for`` field; donations always come from 'streamlabs'.
    """
    raw = str(message.get("for") or "").strip().lower()
    if raw in _SL_PLATFORM:
        return _SL_PLATFORM[raw]
    if etype == "donation":
        return "streamlabs"
    # Fold "<platform>_account" → "<platform>" for anything not pre-mapped.
    return raw.replace("_account", "") if raw else ""


# Streamlabs top-level "type" → our canonical event type. Streamlabs uses
# 'bits' for cheers and forwards YouTube Super Chats as 'superchat'.
_SL_TYPE_ALIAS = {
    "donation": "donation",
    "follow": "follow",
    "subscription": "subscription",
    "resub": "resub",
    "submysterygift": "giftsub",
    "membershipgift": "giftsub",
    "bits": "cheer",
    "host": "host",
    "raid": "raid", "raids": "raid",
    "superchat": "donation", "superchats": "donation",
}


def _sl_item_type(base_type: str, item: dict[str, Any]) -> str:
    """Refine a per-item type — a 'subscription' may really be a resub."""
    sub_type = str(item.get("sub_type") or "").strip().lower()
    if base_type == "subscription" and sub_type in {"resub", "resubscription"}:
        return "resub"
    return base_type


def from_streamlabs(message: dict[str, Any]) -> list[StreamEvent]:
    """Streamlabs socket 'event' payload: {type, message:[{...}], for}.

    Handles donations, Twitch follows/subs/resubs/bits/hosts/raids, YouTube
    follows/subs/Super Chats, etc. Each linked platform is tagged via ``for``.
    """
    out: list[StreamEvent] = []
    if not isinstance(message, dict):
        return out
    raw_type = str(message.get("type") or "").strip().lower()
    base_type = _SL_TYPE_ALIAS.get(raw_type, raw_type)
    if base_type not in EVENT_TYPES:
        return out
    platform = _sl_platform(message, base_type)
    is_superchat = raw_type in {"superchat", "superchats"}
    items = message.get("message")
    if not isinstance(items, list):
        items = [items] if isinstance(items, dict) else []
    for it in items:
        if not isinstance(it, dict):
            continue
        etype = _sl_item_type(base_type, it)
        amount = _to_float(it.get("amount") or 0)
        # YouTube Super Chat amounts arrive in micros (2000000 == $2.00).
        if is_superchat and amount >= 1000:
            amount = round(amount / 1_000_000.0, 2)
        out.append(StreamEvent(
            type=etype,
            user=str(it.get("name") or it.get("from") or it.get("displayName") or "someone"),
            amount=amount,
            currency=str(it.get("currency") or "USD"),
            months=_to_int(it.get("months") or it.get("streak") or 0),
            tier=str(it.get("sub_plan") or it.get("tier") or ""),
            viewers=_to_int(it.get("raiders") or it.get("viewers") or 0),
            message=str(it.get("message") or it.get("comment") or ""),
            source="streamlabs",
            platform=platform,
            event_id=str(it.get("_id") or message.get("event_id") or ""),
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


# StreamElements Astro (wss://astro.streamelements.com) activity type → ours.
_SE_ASTRO_TYPE = {
    "follow": "follow", "follower": "follow",
    "subscriber": "subscription", "sponsor": "subscription",
    "tip": "donation", "superchat": "donation",
    "charitycampaigndonation": "donation",
    "cheer": "cheer", "cheerpurchase": "cheer",
    "raid": "raid", "host": "host",
    "communitygiftpurchase": "giftsub", "subgift": "giftsub",
}


def _se_astro_tip(data: dict[str, Any]) -> StreamEvent | None:
    """channel.tips payload → donation."""
    don = data.get("donation") if isinstance(data.get("donation"), dict) else {}
    user = don.get("user") if isinstance(don.get("user"), dict) else {}
    return StreamEvent(
        type="donation",
        user=str(user.get("username") or user.get("name") or "someone"),
        amount=_to_float(don.get("amount") or 0),
        currency=str(don.get("currency") or "USD"),
        message=str(don.get("message") or ""),
        source="streamelements",
        platform=str(data.get("provider") or "streamelements"),
        event_id=str(data.get("_id") or data.get("transactionId") or ""),
        raw=data,
    )


def _se_astro_activity(data: dict[str, Any]) -> StreamEvent | None:
    """channel.activities payload → StreamEvent (follow/sub/cheer/raid/...)."""
    atype = str(data.get("type") or "").strip().lower()
    etype = _SE_ASTRO_TYPE.get(atype)
    if not etype:
        return None
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    viewers = 0
    if etype in {"raid", "host"}:
        viewers = _to_int(inner.get("raiders") or inner.get("viewers") or inner.get("amount") or 0)
    return StreamEvent(
        type=etype,
        user=str(inner.get("displayName") or inner.get("username") or inner.get("name") or "someone"),
        amount=_to_float(inner.get("amount") or 0) if etype in {"cheer", "donation"} else 0.0,
        currency=str(inner.get("currency") or "USD"),
        months=_to_int(inner.get("months") or inner.get("streak") or 0),
        tier=str(inner.get("tier") or ""),
        viewers=viewers,
        message=str(inner.get("message") or inner.get("comment") or ""),
        source="streamelements",
        platform=str(data.get("provider") or "streamelements"),
        event_id=str(data.get("_id") or data.get("activityId") or ""),
        raw=data,
    )


def from_streamelements_astro(envelope: dict[str, Any]) -> StreamEvent | None:
    """Astro server 'message' frame → StreamEvent.

    Routes by topic: ``channel.tips`` (donations) and ``channel.activities``
    (follows/subs/cheers/raids/hosts/gift subs/Super Chats).
    """
    if not isinstance(envelope, dict):
        return None
    topic = str(envelope.get("topic") or "")
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    if topic == "channel.tips":
        return _se_astro_tip(data)
    if topic == "channel.activities":
        return _se_astro_activity(data)
    return None


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
