"""Scripted baseline bots. They exist to test the engine and to give LLM agents something to beat."""

from __future__ import annotations

import random
from typing import Any

from pokertable_agent.base import Decision

RANK_ORDER = "23456789TJQKA"


class FoldBot:
    """Checks when free, folds otherwise. The floor of any leaderboard."""

    name = "fold-bot"

    def decide(self, obs: dict[str, Any], error: str | None = None) -> Decision:
        return Decision("check" if "check" in obs["legal_actions"] else "fold")


class AlwaysCallBot:
    """The calling station. Never folds, never raises."""

    name = "call-bot"

    def decide(self, obs: dict[str, Any], error: str | None = None) -> Decision:
        return Decision("check" if "check" in obs["legal_actions"] else "call")


class RandomBot:
    name = "random-bot"

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def decide(self, obs: dict[str, Any], error: str | None = None) -> Decision:
        legal = obs["legal_actions"]
        a = self.rng.choice(legal)
        if a in ("bet", "raise"):
            lo, hi = obs["min_raise_to"], obs["max_raise_to"]
            amt = lo if self.rng.random() < 0.7 else self.rng.randint(lo, hi)
            return Decision(a, amt)
        return Decision(a)


def preflop_strength(cards: list[str]) -> float:
    """Crude 0..1 preflop hand strength (Chen-like)."""
    r1, s1 = cards[0][0], cards[0][1]
    r2, s2 = cards[1][0], cards[1][1]
    hi, lo = sorted([RANK_ORDER.index(r1), RANK_ORDER.index(r2)], reverse=True)
    score = {12: 10, 11: 8, 10: 7, 9: 6}.get(hi, (hi + 2) / 2)
    if hi == lo:
        score = max(5, score * 2)
    if s1 == s2:
        score += 2
    gap = hi - lo
    if hi != lo:
        score -= {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
        if gap <= 1 and hi < 10:
            score += 1
    return max(0.0, min(1.0, score / 20))


def made_hand_strength(hole: list[str], board: list[str]) -> float:
    """0..1 relative strength of the best 5-card hand using phevaluator (lower rank number is better)."""
    from phevaluator import evaluate_cards

    rank = evaluate_cards(*hole, *board)  # 1 (royal flush) .. 7462 (worst high card)
    return 1.0 - (rank - 1) / 7461


class TightAggressiveBot:
    """Preflop chart by strength, postflop bets made hands and folds to pressure without equity.

    It is not good. It is consistent, which is what a baseline needs.
    """

    name = "tag-bot"

    def __init__(self, seed: int | None = None, aggression: float = 0.6) -> None:
        self.rng = random.Random(seed)
        self.aggression = aggression

    def decide(self, obs: dict[str, Any], error: str | None = None) -> Decision:
        legal = obs["legal_actions"]
        hole, board = obs["hole_cards"], obs["board"]
        to_call = obs.get("amount_to_call", 0)
        pot = max(obs.get("pot", 0), 1)
        bb = obs["blinds"]["big"]
        can_raise = "raise" in legal or "bet" in legal
        raise_word = "bet" if "bet" in legal else "raise"
        if not board:
            s = preflop_strength(hole)
            if s >= 0.42 and can_raise:
                target = max(obs["min_raise_to"], min(obs["max_raise_to"], 3 * bb + to_call))
                return Decision(raise_word, target)
            if s >= 0.28 and to_call <= 3 * bb:
                return Decision("call" if "call" in legal else "check")
            return Decision("check" if "check" in legal else "fold")
        s = made_hand_strength(hole, board)
        pot_odds = to_call / (pot + to_call) if to_call else 0
        if s >= 0.75 and can_raise and self.rng.random() < self.aggression:
            target = max(obs["min_raise_to"], min(obs["max_raise_to"], int(0.66 * pot) + to_call))
            return Decision(raise_word, target)
        if s >= 0.5 or (to_call and s > pot_odds + 0.1):
            return Decision("call" if "call" in legal else "check")
        return Decision("check" if "check" in legal else "fold")


def make_bot(kind: str, seed: int | None = None):
    kinds = {
        "fold": FoldBot,
        "call": AlwaysCallBot,
        "random": lambda: RandomBot(seed),
        "tag": lambda: TightAggressiveBot(seed),
    }
    if kind not in kinds:
        raise ValueError(f"unknown bot '{kind}'; choose from {sorted(kinds)}")
    return kinds[kind]()
