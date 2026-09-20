"""A table: seats, the hand loop, filtered observations, idempotent actions, chat, timeouts.

Pure Python, no I/O, no asyncio. Drivers (the HTTP server, the simulation
runner) call ``tick(now)`` and react to ``version`` changes. Everything an agent
may see passes through ``observation``; that is the only place hidden state is
filtered, so it is the only place a leak could happen.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

from pokertable.core import Dealer, Hand, HandResult, IllegalAction, SeatEntry

from .identity import Identity

CHAT_KEEP = 50
CHAT_MAX_LEN = 280


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra

    def as_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, **self.extra}


@dataclass
class GameConfig:
    game_id: str
    name: str = "Table"
    small_blind: int = 5
    big_blind: int = 10
    starting_stack: int = 1000
    max_seats: int = 6
    decision_seconds: float = 90.0
    hand_limit: int = 100
    hand_pause_seconds: float = 3.0
    reveal_all_after_game: bool = True
    open_join: bool = True
    auto_rebuy: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Seat:
    seat: int
    identity_id: str
    name: str
    stack: int
    sitting_out: bool = False
    timeouts_in_row: int = 0
    # telemetry for the agent panel
    connector: str = ""
    last_request_at: float | None = None
    last_latency_ms: float | None = None
    timeouts: int = 0
    invalid_actions: int = 0
    decisions: int = 0
    hands_played: int = 0
    net: int = 0

    def public(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "name": self.name,
            "stack": self.stack,
            "sitting_out": self.sitting_out,
        }


@dataclass
class ChatMessage:
    seat: int | None
    name: str
    text: str
    hand_number: int
    ts: float


@dataclass
class TurnState:
    token: str
    seat: int
    deadline: float
    corrections_left: int = 1


class Game:
    def __init__(self, config: GameConfig, dealer: Dealer | None = None) -> None:
        self.config = config
        self.dealer = dealer or Dealer()
        self.seats: dict[int, Seat] = {}
        self.status = "waiting"  # waiting | running | paused | finished
        self.hand: Hand | None = None
        self.hand_number = 0
        self.button_seat: int | None = None
        self.version = 0
        self.turn: TurnState | None = None
        self.next_hand_at: float | None = None
        self.chat: list[ChatMessage] = []
        self._request_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self.completed: list[dict[str, Any]] = []  # hand records with private data, for persistence
        self.on_hand_complete: list[Callable[[Game, Hand, HandResult], None]] = []
        self.on_change: list[Callable[[Game], None]] = []
        self.created_at = time.time()
        self.finished_reason: str | None = None

    # ---- seating ---------------------------------------------------------

    def seat_of(self, identity_id: str) -> Seat | None:
        for s in self.seats.values():
            if s.identity_id == identity_id:
                return s
        return None

    def add_seat(self, identity: Identity, seat: int | None = None, stack: int | None = None, connector: str = "") -> Seat:
        if not identity.can_play:
            raise ServiceError(403, "forbidden", f"role {identity.role} cannot take a seat")
        existing = self.seat_of(identity.id)
        if existing:
            if connector:
                existing.connector = connector
            return existing
        if self.status == "finished":
            raise ServiceError(409, "game_finished", "game is finished")
        if seat is None:
            free = [i for i in range(1, self.config.max_seats + 1) if i not in self.seats]
            if not free:
                raise ServiceError(409, "table_full", "no free seat")
            seat = free[0]
        if seat in self.seats or not 1 <= seat <= self.config.max_seats:
            raise ServiceError(409, "seat_taken", f"seat {seat} is not available")
        s = Seat(seat=seat, identity_id=identity.id, name=identity.name, stack=stack or self.config.starting_stack, connector=connector)
        self.seats[seat] = s
        self._bump()
        return s

    def remove_seat(self, seat: int) -> None:
        if self.hand and not self.hand.finished and seat in self.hand.all_hole_cards():
            raise ServiceError(409, "hand_in_progress", "cannot remove a seat during a hand")
        self.seats.pop(seat, None)
        self._bump()

    # ---- lifecycle -------------------------------------------------------

    def start(self, now: float | None = None) -> None:
        if self.status not in ("waiting", "paused"):
            raise ServiceError(409, "bad_state", f"cannot start a game that is {self.status}")
        if len(self._playable_seats()) < 2:
            raise ServiceError(409, "not_enough_players", "need at least two seated players with chips")
        self.status = "running"
        now = now if now is not None else time.time()
        self.next_hand_at = now
        self._bump()
        if self.hand is None or self.hand.finished:
            self._start_hand(now)

    def pause(self) -> None:
        if self.status == "running":
            self.status = "paused"
            self._bump()

    def stop(self, reason: str = "stopped by admin") -> None:
        self.status = "finished"
        self.finished_reason = reason
        self._bump()

    def _playable_seats(self) -> list[Seat]:
        return [s for s in self.seats.values() if s.stack > 0 and not s.sitting_out]

    def tick(self, now: float) -> bool:
        """Advance time. Returns True if state changed."""
        before = self.version
        if self.status != "running":
            return False
        if self.hand is None or self.hand.finished:
            if self.next_hand_at is not None and now >= self.next_hand_at:
                self._start_hand(now)
        elif self.turn and now >= self.turn.deadline:
            self._timeout(now)
        return self.version != before

    def _start_hand(self, now: float) -> None:
        if self.config.hand_limit and self.hand_number >= self.config.hand_limit:
            self.stop("hand limit reached")
            return
        if self.config.auto_rebuy:
            for s in self.seats.values():
                if s.stack <= 0:
                    s.stack = self.config.starting_stack
                    s.sitting_out = False
        players = self._playable_seats()
        if len(players) < 2:
            self.stop("fewer than two players with chips")
            return
        order = sorted(s.seat for s in players)
        self.button_seat = self._next_button(order)
        self.hand_number += 1
        entries = [SeatEntry(seat=s.seat, name=s.name, stack=s.stack) for s in sorted(players, key=lambda x: x.seat)]
        self.hand = Hand(
            hand_id=self.hand_number,
            seats=entries,
            button_seat=self.button_seat,
            small_blind=self.config.small_blind,
            big_blind=self.config.big_blind,
            deck=self.dealer.shuffled_deck(),
        )
        for s in players:
            s.hands_played += 1
        self.next_hand_at = None
        self._after_state_change(now)

    def _next_button(self, order: list[int]) -> int:
        if self.button_seat is None:
            return order[0]
        for seat in order:
            if seat > self.button_seat:
                return seat
        return order[0]

    def _after_state_change(self, now: float) -> None:
        hand = self.hand
        assert hand is not None
        if hand.finished:
            self.turn = None
            self._finish_hand(now)
        else:
            actor = hand.actor_seat
            assert actor is not None
            self.turn = TurnState(token="t_" + secrets.token_hex(4), seat=actor, deadline=now + self.config.decision_seconds)
        self._bump()

    def _finish_hand(self, now: float) -> None:
        hand = self.hand
        assert hand is not None and hand.result is not None
        res = hand.result
        for seat, stack in res.final_stacks.items():
            s = self.seats[seat]
            s.stack = stack
            s.net += res.payoffs[seat]
            if s.stack <= 0 and not self.config.auto_rebuy:
                s.sitting_out = True
        self.completed.append(hand.record(include_private=True))
        for cb in self.on_hand_complete:
            cb(self, hand, res)
        self.next_hand_at = now + self.config.hand_pause_seconds
        if self.config.hand_limit and self.hand_number >= self.config.hand_limit:
            self.status = "finished"
            self.finished_reason = "hand limit reached"
        elif len(self._playable_seats()) < 2 and not self.config.auto_rebuy:
            self.status = "finished"
            self.finished_reason = "fewer than two players with chips"

    def _timeout(self, now: float) -> None:
        hand, turn = self.hand, self.turn
        assert hand is not None and turn is not None
        seat = self.seats[turn.seat]
        seat.timeouts += 1
        seat.timeouts_in_row += 1
        legal = hand.legal_actions(turn.seat)
        action = "check" if "check" in legal.actions else "fold"
        hand.apply(turn.seat, action)
        hand.events.append({"seq": len(hand.events), "type": "timeout", "seat": turn.seat, "fallback": action})
        if seat.timeouts_in_row >= 3:
            seat.sitting_out = True
        self._after_state_change(now)

    # ---- agent-facing operations ----------------------------------------

    def _require_seat(self, identity: Identity) -> Seat:
        s = self.seat_of(identity.id)
        if s is None:
            raise ServiceError(403, "not_seated", "identity has no seat at this game")
        return s

    def observation(self, identity: Identity, now: float | None = None) -> dict[str, Any]:
        """The only function that produces a live view. Filters by identity."""
        now = now if now is not None else time.time()
        seat = self.seat_of(identity.id)
        obs: dict[str, Any] = {
            "game_id": self.config.game_id,
            "game_status": self.status,
            "state_version": self.version,
            "hand_id": self.hand_number if self.hand else None,
            "phase": self.hand.phase if self.hand else None,
            "my_seat": seat.seat if seat else None,
            "my_turn": False,
            "button_seat": self.button_seat,
            "blinds": {"small": self.config.small_blind, "big": self.config.big_blind},
            "board": self.hand.board if self.hand else [],
            "pot": self.hand.pot_total if self.hand else 0,
            "pots": self.hand.pots() if self.hand else [],
            "seats": self._seat_views(),
            "hand_actions": self.hand.hand_actions if self.hand else [],
            "recent_chat": [{"seat": m.seat, "name": m.name, "text": m.text} for m in self.chat[-8:]],
            "acting_seat": self.turn.seat if self.turn else None,
            "deadline_utc": _iso(self.turn.deadline) if self.turn else None,
            "seconds_left": max(0.0, round(self.turn.deadline - now, 1)) if self.turn else None,
            "next_hand_in": max(0.0, round(self.next_hand_at - now, 1)) if self.next_hand_at and self.status == "running" else None,
            "last_hand": self._last_hand_public(),
        }
        if seat and self.hand and seat.seat in self.hand.all_hole_cards():
            obs["hole_cards"] = self.hand.hole_cards(seat.seat)
            obs["stack"] = self.hand.stack(seat.seat)
            if self.turn and self.turn.seat == seat.seat and not self.hand.finished:
                legal = self.hand.legal_actions(seat.seat)
                obs["my_turn"] = True
                obs["turn_token"] = self.turn.token
                obs["legal_actions"] = legal.actions
                obs["amount_to_call"] = legal.call_amount
                obs["min_raise_to"] = legal.min_raise_to
                obs["max_raise_to"] = legal.max_raise_to
        return obs

    def _seat_views(self) -> list[dict[str, Any]]:
        views = []
        hand = self.hand
        positions = hand.positions() if hand else {}
        for s in sorted(self.seats.values(), key=lambda x: x.seat):
            v = s.public()
            if hand and s.seat in hand.all_hole_cards():
                v["stack"] = hand.stack(s.seat)
                v["bet"] = hand.bet(s.seat)
                v["status"] = hand.status(s.seat)
                v["position"] = positions.get(s.seat)
                if hand.finished and hand.result and s.seat in hand.result.shown_cards:
                    v["shown_cards"] = hand.result.shown_cards[s.seat]
            else:
                v["bet"] = 0
                v["status"] = "sitting_out" if s.sitting_out else "waiting"
            views.append(v)
        return views

    def _last_hand_public(self) -> dict[str, Any] | None:
        if not self.completed:
            return None
        rec = self.completed[-1]
        return {k: rec[k] for k in ("hand_id", "board", "payoffs", "winners", "shown_cards")}

    def legal_actions(self, identity: Identity) -> dict[str, Any]:
        seat = self._require_seat(identity)
        if not self.hand or self.hand.finished:
            return {"actions": [], "my_turn": False}
        legal = self.hand.legal_actions(seat.seat)
        return {**legal.as_dict(), "my_turn": self.hand.actor_seat == seat.seat, "turn_token": self.turn.token if self.turn and self.turn.seat == seat.seat else None}

    def submit_action(self, identity: Identity, req: dict[str, Any], now: float | None = None) -> dict[str, Any]:
        now = now if now is not None else time.time()
        seat = self._require_seat(identity)
        request_id = str(req.get("request_id") or "")
        if not request_id:
            raise ServiceError(400, "missing_request_id", "request_id is required")
        cache_key = (identity.id, request_id)
        if cache_key in self._request_cache:
            return {**self._request_cache[cache_key], "duplicate": True}
        seat.decisions += 1
        seat.last_request_at = now
        if self.status != "running" or not self.hand or self.hand.finished:
            raise ServiceError(409, "no_hand", "no hand in progress", observation=self.observation(identity, now))
        if req.get("hand_id") is not None and int(req["hand_id"]) != self.hand_number:
            raise ServiceError(409, "stale_hand", f"hand {req['hand_id']} is not the current hand", observation=self.observation(identity, now))
        turn = self.turn
        if turn is None or turn.seat != seat.seat:
            raise ServiceError(409, "not_your_turn", "it is not this seat's turn", observation=self.observation(identity, now))
        if req.get("turn_token") and req["turn_token"] != turn.token:
            raise ServiceError(409, "stale_turn_token", "turn token does not match the current turn", observation=self.observation(identity, now))
        try:
            event = self.hand.apply(seat.seat, str(req.get("action", "")), req.get("amount"))
        except IllegalAction as e:
            seat.invalid_actions += 1
            raise ServiceError(400, "illegal_action", e.message, legal_actions=e.legal.as_dict() if e.legal else None, seconds_left=max(0.0, turn.deadline - now))
        seat.timeouts_in_row = 0
        self._after_state_change(now)
        result = {"accepted": True, "applied": event, "hand_id": self.hand_number, "state_version": self.version, "hand_complete": self.hand.finished}
        self._request_cache[cache_key] = result
        if len(self._request_cache) > 5000:
            for k in list(self._request_cache)[:1000]:
                self._request_cache.pop(k, None)
        return result

    def say(self, identity: Identity, text: str, now: float | None = None) -> ChatMessage:
        now = now if now is not None else time.time()
        text = (text or "").strip()[:CHAT_MAX_LEN]
        if not text:
            raise ServiceError(400, "empty_message", "message is empty")
        seat = self.seat_of(identity.id)
        msg = ChatMessage(seat=seat.seat if seat else None, name=identity.name, text=text, hand_number=self.hand_number, ts=now)
        self.chat.append(msg)
        if len(self.chat) > CHAT_KEEP:
            del self.chat[: len(self.chat) - CHAT_KEEP]
        self._bump()
        return msg

    # ---- public / admin views -------------------------------------------

    def public_state(self, now: float | None = None) -> dict[str, Any]:
        """What an observer sees. Same filter as a non-seated identity."""
        observer = Identity(id="__observer__", name="observer", role="observer", key_hash="")
        return self.observation(observer, now)

    def agent_panel(self, now: float | None = None) -> list[dict[str, Any]]:
        now = now if now is not None else time.time()
        out = []
        for s in sorted(self.seats.values(), key=lambda x: x.seat):
            out.append({
                "seat": s.seat, "name": s.name, "identity_id": s.identity_id, "connector": s.connector or "unknown",
                "stack": s.stack, "net": s.net, "hands_played": s.hands_played, "decisions": s.decisions,
                "timeouts": s.timeouts, "invalid_actions": s.invalid_actions,
                "last_request_ago": None if s.last_request_at is None else round(now - s.last_request_at, 1),
                "last_latency_ms": s.last_latency_ms, "sitting_out": s.sitting_out,
                "acting": bool(self.turn and self.turn.seat == s.seat),
            })
        return out

    def snapshot(self) -> dict[str, Any]:
        """Persistable between-hands state. Never contains a live hand."""
        return {
            "config": self.config.as_dict(),
            "status": self.status,
            "hand_number": self.hand_number,
            "button_seat": self.button_seat,
            "finished_reason": self.finished_reason,
            "seats": [asdict(s) for s in self.seats.values()],
        }

    @classmethod
    def from_snapshot(cls, snap: dict[str, Any], dealer: Dealer | None = None) -> "Game":
        g = cls(GameConfig(**snap["config"]), dealer)
        g.hand_number = snap["hand_number"]
        g.button_seat = snap["button_seat"]
        g.finished_reason = snap.get("finished_reason")
        for sd in snap["seats"]:
            g.seats[sd["seat"]] = Seat(**sd)
        # A game that was running when the process died comes back paused: an
        # administrator must confirm before play resumes. The interrupted hand
        # was never persisted, so it cannot silently continue.
        g.status = "paused" if snap["status"] == "running" else snap["status"]
        return g

    def _bump(self) -> None:
        self.version += 1
        for cb in self.on_change:
            cb(self)


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
