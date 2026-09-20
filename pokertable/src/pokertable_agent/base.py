"""The agent interface. An agent turns an observation into one decision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class Decision:
    action: str
    amount: int | None = None
    say: str | None = None
    reasoning: str | None = None

    def as_request(self) -> dict[str, Any]:
        body: dict[str, Any] = {"action": self.action}
        if self.amount is not None:
            body["amount"] = int(self.amount)
        return body


class Agent(Protocol):
    name: str

    def decide(self, observation: dict[str, Any], error: str | None = None) -> Decision:
        """Return a decision for this observation. ``error`` carries the server's
        rejection of the previous attempt on the same turn, if any."""
        ...


def clamp_decision(decision: Decision, obs: dict[str, Any]) -> Decision:
    """Make a decision legal where the intent is unambiguous. Never invents aggression."""
    legal = set(obs.get("legal_actions") or [])
    a = decision.action.lower().strip()
    if a in ("bet", "raise"):
        if "bet" in legal or "raise" in legal:
            a = "bet" if "bet" in legal else "raise"
            lo, hi = obs.get("min_raise_to"), obs.get("max_raise_to")
            amt = decision.amount if decision.amount is not None else lo
            if lo is not None and hi is not None:
                amt = max(lo, min(hi, int(amt)))
            return Decision(a, amt, decision.say, decision.reasoning)
        a = "call" if "call" in legal else "check"
    if a == "check" and "check" not in legal:
        a = "call" if "call" in legal else "fold"
    if a == "call" and "call" not in legal:
        a = "check" if "check" in legal else "fold"
    if a not in legal:
        a = "check" if "check" in legal else "fold"
    return Decision(a, None, decision.say, decision.reasoning)
