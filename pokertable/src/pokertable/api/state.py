"""Application state: registry, repository, live games, change notification, ticker."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from pokertable.config import ServerConfig
from pokertable.core import Dealer, Hand, HandResult
from pokertable.db import Repository
from pokertable.db.repo import hand_result_rows
from pokertable.service import Game, GameConfig, IdentityRegistry, ServiceError
from pokertable.service.identity import Identity


class AppState:
    def __init__(self, config: ServerConfig, repo: Repository | None = None) -> None:
        self.config = config
        self.repo = repo or Repository(config.database)
        self.registry = IdentityRegistry()
        self.games: dict[str, Game] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._ticker: asyncio.Task[None] | None = None
        self.started_at = time.time()
        self._load()

    # ---- startup / recovery ---------------------------------------------

    def _load(self) -> None:
        for ident in self.repo.load_identities():
            self.registry.load(ident)
        for ic in self.config.identities:
            ident, _ = self.registry.add(ic.name, ic.role, key=ic.key)
            self.repo.save_identity(ident)
        for row in self.repo.load_games():
            game = Game.from_snapshot(row["snapshot"])
            self._attach(game)
            if game.status != row["status"]:
                # was running when the process died: now paused pending admin confirmation
                self.repo.save_game(game.config.game_id, game.config.name, game.status, game.snapshot())

    def _attach(self, game: Game) -> None:
        self.games[game.config.game_id] = game
        self._events[game.config.game_id] = asyncio.Event()
        game.on_hand_complete.append(self._persist_hand)
        game.on_change.append(self._notify)

    def create_game(self, cfg: GameConfig, dealer: Dealer | None = None) -> Game:
        if cfg.game_id in self.games:
            raise ServiceError(409, "exists", f"game {cfg.game_id} already exists")
        game = Game(cfg, dealer)
        self._attach(game)
        self.save_game(game)
        return game

    def get_game(self, game_id: str) -> Game:
        game = self.games.get(game_id)
        if game is None:
            raise ServiceError(404, "not_found", f"no game {game_id}")
        return game

    def save_game(self, game: Game) -> None:
        self.repo.save_game(game.config.game_id, game.config.name, game.status, game.snapshot())

    def _persist_hand(self, game: Game, hand: Hand, res: HandResult) -> None:
        record = hand.record(include_private=True)
        seat_identity = {s.seat: (s.identity_id, s.name) for s in game.seats.values()}
        self.repo.save_hand(game.config.game_id, record, hand_result_rows(game.config.game_id, record, seat_identity))
        self.save_game(game)

    # ---- change notification --------------------------------------------

    def _notify(self, game: Game) -> None:
        ev = self._events.get(game.config.game_id)
        if ev is not None:
            ev.set()
            self._events[game.config.game_id] = asyncio.Event()

    async def wait_for_change(self, game_id: str, version: int, timeout: float) -> bool:
        """Wait until the game's version differs from ``version``. Returns True if it changed."""
        deadline = time.monotonic() + timeout
        while True:
            game = self.games[game_id]
            if game.version != version:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            ev = self._events[game_id]
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(ev.wait(), timeout=min(remaining, 5.0))

    # ---- ticker ----------------------------------------------------------

    async def start(self) -> None:
        self._ticker = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        if self._ticker:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker
        self.repo.close()

    async def _tick_loop(self) -> None:
        while True:
            now = time.time()
            for game in list(self.games.values()):
                before = game.status
                if game.tick(now) and (game.status != before or (game.hand and game.hand.finished)):
                    self.save_game(game)
            await asyncio.sleep(self.config.tick_seconds)

    # ---- views -----------------------------------------------------------

    def hand_record_for(self, game: Game, record: dict[str, Any], identity: Identity | None) -> dict[str, Any]:
        """Apply the visibility policy to a stored hand record."""
        reveal = (
            identity is not None
            and identity.can_analyse
            and game.config.reveal_all_after_game
            and game.status == "finished"
        )
        if reveal:
            return record
        return {**record, "hole_cards": {}, "events": [e for e in record["events"] if not e.get("private")]}
