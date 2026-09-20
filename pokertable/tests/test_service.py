"""Idempotency, turn tokens, timeouts, restart recovery."""

from pokertable.core import Dealer
from pokertable.db import Repository
from pokertable.service import Game, GameConfig, Identity, Role, ServiceError
from pokertable.service.stats import player_stats, wilson, bb100
from pokertable.api.state import AppState
from pokertable.config import ServerConfig, IdentityConfig
import pytest


def make_game(**kw):
    cfg = GameConfig(game_id="g", hand_limit=5, hand_pause_seconds=0, decision_seconds=10, **kw)
    g = Game(cfg, Dealer(seed=11))
    ids = {i: Identity(id=f"p{i}", name=f"p{i}", role=Role.PLAYER, key_hash="") for i in (1, 2, 3)}
    for i in ids.values():
        g.add_seat(i)
    g.start(0.0)
    g.tick(0.0)
    return g, ids


def test_duplicate_request_id_is_not_applied_twice():
    g, ids = make_game()
    seat = g.hand.actor_seat
    obs = g.observation(ids[seat], 0.0)
    r1 = g.submit_action(ids[seat], {"request_id": "x", "turn_token": obs["turn_token"], "action": "call"}, 1.0)
    v = g.version
    r2 = g.submit_action(ids[seat], {"request_id": "x", "turn_token": obs["turn_token"], "action": "fold"}, 1.0)
    assert r2["duplicate"] and r2["applied"] == r1["applied"]
    assert g.version == v


def test_stale_turn_token_and_wrong_seat_rejected():
    g, ids = make_game()
    seat = g.hand.actor_seat
    tok = g.observation(ids[seat], 0.0)["turn_token"]
    g.submit_action(ids[seat], {"request_id": "1", "turn_token": tok, "action": "call"}, 1.0)
    nxt = g.hand.actor_seat
    with pytest.raises(ServiceError) as e:
        g.submit_action(ids[nxt], {"request_id": "2", "turn_token": tok, "action": "call"}, 1.0)
    assert e.value.code == "stale_turn_token" and "observation" in e.value.extra
    with pytest.raises(ServiceError) as e:
        g.submit_action(ids[seat], {"request_id": "3", "action": "call"}, 1.0)
    assert e.value.code == "not_your_turn"
    with pytest.raises(ServiceError) as e:
        g.submit_action(ids[nxt], {"request_id": "4", "hand_id": 99, "action": "call"}, 1.0)
    assert e.value.code == "stale_hand"


def test_illegal_action_returns_legal_range_and_counts():
    g, ids = make_game()
    seat = g.hand.actor_seat
    with pytest.raises(ServiceError) as e:
        g.submit_action(ids[seat], {"request_id": "1", "action": "raise", "amount": 1}, 1.0)
    assert e.value.code == "illegal_action" and e.value.extra["legal_actions"]["min_raise_to"] == 20
    assert g.seats[seat].invalid_actions == 1


def test_timeout_checks_when_free_else_folds_and_sits_out_after_three():
    g, ids = make_game()
    seat = g.hand.actor_seat
    g.tick(11.0)
    assert g.seats[seat].timeouts == 1
    assert g.hand.status(seat) == "folded"
    t = 11.0
    while g.seats[seat].timeouts < 3 and g.status == "running":
        t += 11
        g.tick(t)
    assert g.seats[seat].sitting_out


def test_restart_recovery_pauses_and_discards_live_hand(tmp_path):
    repo = Repository(tmp_path / "p.db")
    cfg = ServerConfig(identities=[IdentityConfig("a", "ka"), IdentityConfig("b", "kb")], database=str(tmp_path / "p.db"))
    import asyncio

    async def first():
        st = AppState(cfg, repo)
        game = st.create_game(GameConfig(game_id="g", hand_limit=10, hand_pause_seconds=0))
        game.add_seat(st.registry.get("a"))
        game.add_seat(st.registry.get("b"))
        game.start()
        game.tick(__import__("time").time())
        assert game.hand is not None and not game.hand.finished
        st.save_game(game)  # snapshot says running, hand 1 live but unpersisted
        return game.hand_number

    hand_no = asyncio.run(first())
    repo2 = Repository(tmp_path / "p.db")
    st2 = AppState(cfg, repo2)
    g2 = st2.games["g"]
    assert g2.status == "paused", "a game that was running when the process died must not continue on its own"
    assert g2.hand is None
    assert repo2.load_hand("g", hand_no) is None, "the interrupted hand was never recorded"
    assert [s.stack for s in g2.seats.values()] == [1000, 1000]


def test_stats_math():
    p, lo, hi = wilson(50, 100)
    assert abs(p - 0.5) < 1e-9 and 0.40 < lo < 0.5 < hi < 0.60
    m, lo, hi = bb100([1.0, -1.0, 2.0, 0.0])
    assert m == 50.0 and lo < m < hi
    rows = [{"identity_id": "x", "name": "x", "big_blind": 10, "net": 10, "vpip": 1, "pfr": 0, "bets_raises": 0, "calls": 1, "went_to_showdown": 1, "won_at_showdown": 1, "timed_out": 0}] * 4
    s = player_stats(rows)["x"]
    assert s["hands"] == 4 and s["net_chips"] == 40 and s["vpip"]["value"] == 100.0 and s["sample_warning"]
