"""No identity can obtain another seat's private cards through any supported interface."""

import pytest
from fastapi.testclient import TestClient

from pokertable.api.app import create_app
from pokertable.config import IdentityConfig, ServerConfig
from pokertable.db import Repository

KEYS = {"admin": "k-admin", "a": "k-a", "b": "k-b", "c": "k-c", "obs": "k-obs", "ana": "k-ana"}


@pytest.fixture
def client():
    cfg = ServerConfig(tick_seconds=0.02, identities=[
        IdentityConfig("admin", KEYS["admin"], "admin"), IdentityConfig("a", KEYS["a"]), IdentityConfig("b", KEYS["b"]), IdentityConfig("c", KEYS["c"]),
        IdentityConfig("obs", KEYS["obs"], "observer"), IdentityConfig("ana", KEYS["ana"], "analyst"),
    ])
    with TestClient(create_app(cfg, Repository(":memory:"))) as c:
        yield c


def H(who):
    return {"authorization": f"Bearer {KEYS[who]}"}


def play_hand(c, game="t1", hands=1):
    """Everyone calls/checks until `hands` hands are done."""
    keys = {"a": "a", "b": "b", "c": "c"}
    done = 0
    for _ in range(200):
        obs = c.get(f"/v1/games/{game}/wait?timeout=1", headers=H("a")).json()
        if obs["game_status"] != "running":
            break
        if obs["hand_id"] and obs["hand_id"] > hands:
            break
        acting = obs["acting_seat"]
        if acting is None:
            continue
        name = next(s["name"] for s in obs["seats"] if s["seat"] == acting)
        o = c.get(f"/v1/games/{game}/observation", headers=H(name)).json()
        if not o["my_turn"]:
            continue
        act = "check" if "check" in o["legal_actions"] else "call"
        c.post(f"/v1/games/{game}/actions", json={"request_id": f"r{_}", "turn_token": o["turn_token"], "action": act}, headers=H(name))


def setup_game(c, **cfg):
    body = {"game_id": "t1", "hand_limit": 3, "decision_seconds": 30, "hand_pause_seconds": 0, **cfg}
    assert c.post("/v1/admin/games", json=body, headers=H("admin")).status_code == 201
    for k in ("a", "b", "c"):
        assert c.post("/v1/games/t1/seats/join", json={}, headers=H(k)).status_code == 200
    assert c.post("/v1/admin/games/t1/start", headers=H("admin")).status_code == 200


def test_live_observation_never_shows_other_hole_cards(client):
    setup_game(client)
    # hand 1 is live now
    seen = {}
    for k in ("a", "b", "c"):
        o = client.get("/v1/games/t1/observation", headers=H(k)).json()
        assert o["my_seat"] is not None and len(o["hole_cards"]) == 2
        seen[k] = o["hole_cards"]
        for s in o["seats"]:
            assert "hole_cards" not in s and "shown_cards" not in s
    assert len({tuple(v) for v in seen.values()}) == 3
    for k in ("obs", "ana", "admin"):
        o = client.get("/v1/games/t1/observation", headers=H(k)).json()
        assert "hole_cards" not in o and "turn_token" not in o and "legal_actions" not in o
    # public stream payload for an anonymous viewer carries nothing private
    assert "hole_cards" not in client.app.state.pt.games["t1"].public_state()


def test_completed_hand_visibility_policy(client):
    setup_game(client, hand_limit=1)
    play_hand(client)
    for _ in range(50):
        if client.get("/v1/games", headers=H("a")).json()[0]["status"] == "finished":
            break
        import time; time.sleep(0.05)
    rec_player = client.get("/v1/games/t1/hands/1", headers=H("a")).json()
    assert rec_player["hole_cards"] == {}
    assert all(not e.get("private") for e in rec_player["events"])
    rec_obs = client.get("/v1/games/t1/hands/1", headers=H("obs")).json()
    assert rec_obs["hole_cards"] == {}
    rec_ana = client.get("/v1/games/t1/hands/1", headers=H("ana")).json()
    assert len(rec_ana["hole_cards"]) == 3, "analyst sees all cards after the game with reveal_all_after_game"
    txt = client.get("/v1/games/t1/export?format=txt", headers=H("a")).text
    assert "Dealt to" not in txt
    js = client.get("/v1/games/t1/export?format=json", headers=H("obs")).json()
    assert all(r["hole_cards"] == {} for r in js)


def test_analyst_sees_nothing_while_game_is_running(client):
    setup_game(client, hand_limit=5)
    play_hand(client, hands=1)
    rec = client.get("/v1/games/t1/hands/1", headers=H("ana")).json()
    assert rec["hole_cards"] == {}, "reveal only after the game ends"


def test_reveal_policy_off_hides_forever(client):
    setup_game(client, hand_limit=1, reveal_all_after_game=False)
    play_hand(client)
    import time
    for _ in range(50):
        if client.get("/v1/games", headers=H("a")).json()[0]["status"] == "finished":
            break
        time.sleep(0.05)
    assert client.get("/v1/games/t1/hands/1", headers=H("admin")).json()["hole_cards"] == {}


def test_roles_are_enforced(client):
    assert client.get("/v1/me").status_code == 401
    assert client.post("/v1/admin/games", json={"game_id": "x"}, headers=H("a")).status_code == 403
    setup_game(client)
    assert client.post("/v1/games/t1/seats/join", json={}, headers=H("obs")).status_code == 403
    assert client.post("/v1/games/t1/actions", json={"request_id": "1", "action": "fold"}, headers=H("obs")).status_code == 403
    assert client.get("/v1/admin/identities", headers=H("ana")).status_code == 403
