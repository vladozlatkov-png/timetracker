"""Model provider adapters. Each exposes ``complete(system, user) -> str``."""

from __future__ import annotations

from typing import Protocol


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


def make_provider(spec: str) -> Provider:
    """``anthropic[:model]`` or ``echo``."""
    kind, _, model = spec.partition(":")
    if kind == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model or None)
    if kind == "echo":
        from .echo import EchoProvider

        return EchoProvider()
    raise ValueError(f"unknown provider '{kind}'")
