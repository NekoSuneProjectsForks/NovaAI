"""osu! driver (offline / solo only).

WARNING: Automating osu! against the official platform (Bancho / osu! servers)
is against the osu! rules and WILL get the account banned. This driver is
intended for OFFLINE / solo / local practice only and surfaces that warning. It
cannot technically detect server state, so the policy is enforced by the warning
and by defaulting ``osu_allow_online`` to false; use at your own risk.

It is a thin specialization of the universal vision+mouse driver. Real-time osu!
performance via screen capture is inherently limited.
"""
from __future__ import annotations

from ..config import Config
from .universal import UniversalGameDriver

BAN_WARNING = (
    "osu! automation against official servers is bannable. This driver is for "
    "OFFLINE/solo practice only. Use at your own risk."
)


class OsuDriver(UniversalGameDriver):
    name = "osu!"

    vision_prompt = (
        "You are the eyes of an osu! playing AI (offline practice). Describe the "
        "screenshot: are we in a menu or mid-map? List visible hit circles and their "
        "approximate screen positions (x,y), any approaching approach-circles, sliders, "
        "and the cursor position. Be concise and concrete with coordinates."
    )

    def __init__(self, config: Config) -> None:
        super().__init__(config, game_name="osu!")

    def start(self) -> None:
        super().start()
        if not getattr(self.config, "osu_allow_online", False):
            # Surface the warning loudly via the standard print path; the Api also
            # shows it in the UI before starting.
            print(f"[NovaAI osu!] {BAN_WARNING}")
