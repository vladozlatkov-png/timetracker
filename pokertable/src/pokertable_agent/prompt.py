"""Observation to prompt. One place, so every model sees the same table."""

from __future__ import annotations

import json
from typing import Any

SYSTEM = """You are playing play-money No-Limit Texas Hold'em against other AI agents and possibly a human.
You receive the table state as JSON and must reply with ONLY a JSON object of the form
{"action": "<fold|check|call|bet|raise>", "amount": <integer, only for bet/raise: the TOTAL amount to bet or raise to>, "say": "<optional short table talk>", "reasoning": "<one sentence>"}
Rules: choose only from legal_actions. For bet/raise, amount must be between min_raise_to and max_raise_to inclusive.
Table talk is optional and never affects the game. Keep it short.
"""

PERSONAS = {
    "tag": "Your style: tight and aggressive. Play few hands, play them hard. Fold to strength without a made hand.",
    "lag": "Your style: loose and aggressive. Apply pressure, bluff selectively, punish passive players.",
    "station": "Your style: sceptical calling station. You hate folding but rarely raise.",
    "maniac": "Your style: maniac. Raise constantly, talk trash, make everyone uncomfortable.",
    "solid": "Your style: solid, balanced, patient. Play position, size bets to the pot, no ego.",
}


def render(obs: dict[str, Any], persona: str | None = None, error: str | None = None) -> tuple[str, str]:
    """Return (system, user) prompt strings."""
    system = SYSTEM + ("\n" + PERSONAS.get(persona, persona) if persona else "")
    view = {k: obs.get(k) for k in (
        "hand_id", "phase", "my_seat", "button_seat", "blinds", "hole_cards", "board", "pot", "pots", "stack",
        "amount_to_call", "min_raise_to", "max_raise_to", "legal_actions", "seats", "hand_actions", "recent_chat", "seconds_left",
    )}
    user = "Table state:\n" + json.dumps(view, indent=1)
    if error:
        user += f"\n\nYour previous reply was rejected by the dealer: {error}\nReply again with a legal action."
    user += "\n\nReply with the JSON object only."
    return system, user
