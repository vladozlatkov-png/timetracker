"""The dealer owns randomness. Nothing outside this module shuffles."""

from __future__ import annotations

import random
import secrets

RANKS = "23456789TJQKA"
SUITS = "shdc"


def new_deck() -> list[str]:
    return [r + s for r in RANKS for s in SUITS]


class Dealer:
    """Produces a freshly shuffled 52-card deck per hand.

    Production play uses the operating system's CSPRNG. Simulation may pass a
    seeded ``random.Random`` so runs are reproducible; the seed is recorded by
    the caller.
    """

    def __init__(self, rng: random.Random | None = None, seed: int | None = None) -> None:
        if rng is not None:
            self.rng = rng
            self.seed = seed
        elif seed is not None:
            self.rng = random.Random(seed)
            self.seed = seed
        else:
            self.rng = secrets.SystemRandom()
            self.seed = None

    def shuffled_deck(self) -> list[str]:
        deck = new_deck()
        self.rng.shuffle(deck)
        return deck
