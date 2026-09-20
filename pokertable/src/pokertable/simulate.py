"""Headless simulation: run the core directly with in-process agents, no HTTP, no timeouts.

    pokertable-simulate --hands 10000 --seed 1 --bots tag,call,random,fold
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from pokertable.core import Dealer
from pokertable.db import Repository
from pokertable.db.repo import hand_result_rows
from pokertable.service import Game, GameConfig, Identity, Role
from pokertable.service.stats import format_table, player_stats


def run(agents: dict[str, Any], hands: int, seed: int | None = None, starting_stack: int = 1000, small_blind: int = 5, big_blind: int = 10,
        repo: Repository | None = None, game_id: str = "sim", max_rejections: int = 3) -> tuple[Game, dict[str, dict[str, Any]]]:
    """``agents`` maps a name to an object with ``decide(observation) -> Decision``."""
    repo = repo or Repository(":memory:")
    cfg = GameConfig(game_id=game_id, name="Simulation", small_blind=small_blind, big_blind=big_blind, starting_stack=starting_stack,
                     max_seats=max(2, len(agents)), decision_seconds=1e9, hand_limit=hands, hand_pause_seconds=0, auto_rebuy=True)
    game = Game(cfg, Dealer(seed=seed))
    idents = {name: Identity(id=name, name=name, role=Role.PLAYER, key_hash="") for name in agents}
    for name, ident in idents.items():
        game.add_seat(ident, connector=f"sim:{getattr(agents[name], 'name', name)}")
    seat_identity = {s.seat: (s.identity_id, s.name) for s in game.seats.values()}
    by_seat = {s.seat: s.identity_id for s in game.seats.values()}

    def persist(g: Game, hand, res) -> None:
        rec = hand.record(include_private=True)
        repo.save_hand(game_id, rec, hand_result_rows(game_id, rec, seat_identity))

    game.on_hand_complete.append(persist)
    game.start(0.0)
    now = 0.0
    n = 0
    while game.status == "running":
        now += 1.0
        game.tick(now)
        if game.turn is None:
            continue
        seat = game.turn.seat
        name = by_seat[seat]
        ident = idents[name]
        obs = game.observation(ident, now)
        error = None
        for attempt in range(max_rejections + 1):
            if attempt == max_rejections:
                fallback = "check" if "check" in obs["legal_actions"] else "fold"
                game.submit_action(ident, {"request_id": f"s{n}f", "action": fallback}, now)
                break
            d = agents[name].decide(obs, error)
            try:
                game.submit_action(ident, {"request_id": f"s{n}-{attempt}", "turn_token": obs["turn_token"], **d.as_request()}, now)
                break
            except Exception as e:  # ServiceError
                error = getattr(e, "message", str(e))
        n += 1
    stats = player_stats([dict(r) for r in repo.hand_results(game_id=game_id)])
    return game, stats


def main(argv: list[str] | None = None) -> None:
    from pokertable_agent.bots import make_bot

    p = argparse.ArgumentParser(description="Headless poker simulation")
    p.add_argument("--hands", type=int, default=1000)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--bots", default="tag,call,random,fold", help="comma-separated bot kinds; repeat a kind to seat several")
    p.add_argument("--stack", type=int, default=1000)
    p.add_argument("--db", help="also persist to this SQLite file")
    args = p.parse_args(argv)
    kinds = [k.strip() for k in args.bots.split(",") if k.strip()]
    agents = {}
    for i, k in enumerate(kinds):
        agents[f"{k}-{i + 1}"] = make_bot(k, seed=(args.seed or 0) * 100 + i)
    t0 = time.perf_counter()
    game, stats = run(agents, args.hands, seed=args.seed, starting_stack=args.stack, repo=Repository(args.db) if args.db else None)
    dt = time.perf_counter() - t0
    print(f"{game.hand_number} hands in {dt:.1f}s ({game.hand_number / dt:.0f} hands/s), seed={args.seed}, reason={game.finished_reason}", file=sys.stderr)
    print(format_table(stats))


if __name__ == "__main__":
    main()
