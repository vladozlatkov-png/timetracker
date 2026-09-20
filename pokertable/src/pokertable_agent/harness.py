"""The agent loop over REST: wait for my turn, decide, act, repeat.

    pokertable-agent --url http://127.0.0.1:8420 --key <api key> --game table-1 --bot tag
    pokertable-agent --url ... --key ... --game ... --llm anthropic --persona lag
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from typing import Any

import httpx

from .base import Agent

log = logging.getLogger("pokertable.agent")


class TableClient:
    def __init__(self, base_url: str, api_key: str, connector: str = "harness", timeout: float = 130.0) -> None:
        self.http = httpx.Client(base_url=base_url.rstrip("/"), headers={"authorization": f"Bearer {api_key}", "x-connector": connector}, timeout=timeout)

    def me(self) -> dict[str, Any]:
        return self._ok(self.http.get("/v1/me"))

    def join(self, game_id: str, seat: int | None = None) -> dict[str, Any]:
        return self._ok(self.http.post(f"/v1/games/{game_id}/seats/join", json={"seat": seat, "connector": self.http.headers["x-connector"]}))

    def wait(self, game_id: str, timeout: float = 30.0) -> dict[str, Any]:
        return self._ok(self.http.get(f"/v1/games/{game_id}/wait", params={"timeout": timeout}))

    def observation(self, game_id: str) -> dict[str, Any]:
        return self._ok(self.http.get(f"/v1/games/{game_id}/observation"))

    def act(self, game_id: str, body: dict[str, Any]) -> httpx.Response:
        return self.http.post(f"/v1/games/{game_id}/actions", json=body)

    def say(self, game_id: str, text: str) -> None:
        self.http.post(f"/v1/games/{game_id}/chat", json={"text": text[:280]})

    @staticmethod
    def _ok(r: httpx.Response) -> dict[str, Any]:
        r.raise_for_status()
        return r.json()


def play(client: TableClient, game_id: str, agent: Agent, max_hands: int | None = None, seat: int | None = None) -> dict[str, Any]:
    """Run until the game finishes. Returns a small summary."""
    info = client.join(game_id, seat)
    log.info("seated at %s as seat %s", game_id, info["seat"])
    stats = {"decisions": 0, "rejections": 0, "hands_seen": set()}
    while True:
        try:
            obs = client.wait(game_id, timeout=30)
        except httpx.HTTPError as e:
            log.warning("wait failed: %s; retrying", e)
            time.sleep(1)
            continue
        if obs["game_status"] == "finished":
            break
        if obs.get("hand_id"):
            stats["hands_seen"].add(obs["hand_id"])
            if max_hands and len(stats["hands_seen"]) > max_hands:
                break
        if not obs.get("my_turn"):
            continue
        error = None
        request_id = str(uuid.uuid4())
        for attempt in range(3):
            decision = agent.decide(obs, error)
            body = {"request_id": request_id, "hand_id": obs["hand_id"], "turn_token": obs["turn_token"], **decision.as_request()}
            try:
                r = client.act(game_id, body)
            except httpx.HTTPError as e:
                log.warning("submit failed: %s; retrying same request_id", e)
                time.sleep(0.5)
                continue
            if r.status_code == 200:
                stats["decisions"] += 1
                if decision.say:
                    client.say(game_id, decision.say)
                log.info("hand %s %s: %s %s", obs["hand_id"], obs["phase"], decision.action, decision.amount or "")
                break
            if r.status_code >= 500:
                log.warning("server error %s; retrying same request_id", r.status_code)
                time.sleep(0.5)
                continue
            try:
                payload = r.json()
            except ValueError:
                payload = {"detail": {"error": "bad_response", "message": r.text[:200]}}
            detail = payload.get("detail", payload)
            code = detail.get("error") if isinstance(detail, dict) else None
            if code == "illegal_action":
                stats["rejections"] += 1
                error = detail.get("message")
                request_id = str(uuid.uuid4())
                log.info("rejected: %s", error)
                continue
            # stale turn, not our turn any more, or duplicate: fetch fresh state
            log.info("action not applied (%s); refreshing", code)
            break
    stats["hands_seen"] = len(stats["hands_seen"])
    return stats


def build_agent(args: argparse.Namespace) -> Agent:
    if args.llm:
        from .llm import LLMAgent
        from .providers import make_provider

        return LLMAgent(make_provider(args.llm), persona=args.persona, name=args.name)
    from .bots import make_bot

    return make_bot(args.bot, seed=args.seed)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Sit an agent at a poker table over REST")
    p.add_argument("--url", default="http://127.0.0.1:8420")
    p.add_argument("--key", required=True, help="API key of a player identity")
    p.add_argument("--game", required=True)
    p.add_argument("--seat", type=int)
    p.add_argument("--bot", default="tag", help="scripted bot: fold | call | random | tag")
    p.add_argument("--llm", help="provider spec, e.g. anthropic or anthropic:claude-opus-5 or echo")
    p.add_argument("--persona", help="persona key (tag, lag, station, maniac, solid) or free text")
    p.add_argument("--name")
    p.add_argument("--seed", type=int)
    p.add_argument("--max-hands", type=int)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    agent = build_agent(args)
    connector = f"harness:{getattr(agent, 'name', 'agent')}"
    client = TableClient(args.url, args.key, connector=connector)
    summary = play(client, args.game, agent, max_hands=args.max_hands, seat=args.seat)
    usage = getattr(getattr(agent, "provider", None), "usage", None)
    if usage:
        summary["provider"] = usage()
    print(summary, file=sys.stderr)


if __name__ == "__main__":
    main()
