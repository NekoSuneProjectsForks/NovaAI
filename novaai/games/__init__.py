"""NovaAI game-playing subsystem.

A pluggable layer that lets NovaAI autonomously play games and narrate what it
is doing. The LLM brain (``GameAgent``) is game-agnostic; each game provides a
``GameDriver`` that knows how to observe and act. Minecraft is implemented via
a Node/Mineflayer bridge; a future vision+keyboard "any game" driver can plug
into the same contract.
"""
from .base import GameCommand, GameDriver, GameObservation

__all__ = ["GameCommand", "GameDriver", "GameObservation"]
