"""An agent that asks a language model what to do."""

from __future__ import annotations

from typing import Any

from .base import Decision, clamp_decision
from .parse import ParseError, parse_decision
from .prompt import render
from .providers import Provider


class LLMAgent:
    def __init__(self, provider: Provider, persona: str | None = None, name: str | None = None, strict: bool = False) -> None:
        self.provider = provider
        self.persona = persona
        self.name = name or provider.name
        self.strict = strict  # if True, do not clamp illegal replies; let the dealer reject them
        self.last_reply: str = ""
        self.parse_failures = 0

    def decide(self, obs: dict[str, Any], error: str | None = None) -> Decision:
        system, user = render(obs, self.persona, error)
        self.last_reply = self.provider.complete(system, user)
        try:
            decision = parse_decision(self.last_reply)
        except ParseError:
            self.parse_failures += 1
            decision = Decision("check" if "check" in obs["legal_actions"] else "fold", reasoning="unparseable reply")
        return decision if self.strict else clamp_decision(decision, obs)
