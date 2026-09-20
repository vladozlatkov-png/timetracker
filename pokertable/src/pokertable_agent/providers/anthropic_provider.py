"""Anthropic adapter. Requires ``pip install anthropic`` and ANTHROPIC_API_KEY (or an ``ant auth login`` profile)."""

from __future__ import annotations

import time


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None, effort: str = "medium", max_tokens: int = 4096) -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or "claude-opus-5"
        self.effort = effort
        self.max_tokens = max_tokens
        self.name = f"anthropic:{self.model}"
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_latency = 0.0

    def complete(self, system: str, user: str) -> str:
        t0 = time.perf_counter()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user}],
        )
        self.total_latency += time.perf_counter() - t0
        self.calls += 1
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        if response.stop_reason == "refusal":
            return '{"action": "fold", "reasoning": "model declined to answer"}'
        return "".join(block.text for block in response.content if block.type == "text")

    def usage(self) -> dict[str, float | int]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "mean_latency_s": round(self.total_latency / self.calls, 2) if self.calls else 0.0,
        }
