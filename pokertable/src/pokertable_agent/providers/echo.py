"""A provider that plays like the calling station. Lets the LLM loop be tested offline."""

from __future__ import annotations

import json


class EchoProvider:
    name = "echo"

    def complete(self, system: str, user: str) -> str:
        legal = "check" if '"check"' in user else "call"
        return json.dumps({"action": legal, "say": "echo echo", "reasoning": "offline test provider"})
