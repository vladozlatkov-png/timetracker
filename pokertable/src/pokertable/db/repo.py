"""SQLite persistence. One file, WAL mode, plain sqlite3.

Completed hands are stored as one JSON record (lossless, replayable) plus one
row per seat in ``hand_results`` for statistics. Live hands are never written.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from pokertable.service.identity import Identity, Role

SCHEMA = """
CREATE TABLE IF NOT EXISTS identities (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, key_hash TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, snapshot TEXT NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS hands (
    game_id TEXT NOT NULL, hand_number INTEGER NOT NULL, record TEXT NOT NULL, completed_at REAL NOT NULL,
    PRIMARY KEY (game_id, hand_number)
);
CREATE TABLE IF NOT EXISTS hand_results (
    game_id TEXT NOT NULL, hand_number INTEGER NOT NULL, seat INTEGER NOT NULL,
    identity_id TEXT NOT NULL, name TEXT NOT NULL, big_blind INTEGER NOT NULL,
    net INTEGER NOT NULL, vpip INTEGER NOT NULL, pfr INTEGER NOT NULL,
    bets_raises INTEGER NOT NULL, calls INTEGER NOT NULL,
    went_to_showdown INTEGER NOT NULL, won_at_showdown INTEGER NOT NULL, timed_out INTEGER NOT NULL,
    PRIMARY KEY (game_id, hand_number, seat)
);
CREATE INDEX IF NOT EXISTS hand_results_identity ON hand_results (identity_id);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT, game_id TEXT NOT NULL, hand_number INTEGER NOT NULL,
    seat INTEGER, name TEXT NOT NULL, text TEXT NOT NULL, ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, identity_id TEXT, connector TEXT,
    game_id TEXT, request_id TEXT, operation TEXT NOT NULL, outcome TEXT NOT NULL,
    latency_ms REAL, error TEXT
);
"""


def _locked(fn):
    def wrapper(self, *a, **kw):
        with self.lock:
            return fn(self, *a, **kw)
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


class Repository:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        if self.path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ---- identities ------------------------------------------------------

    @_locked
    def save_identity(self, ident: Identity) -> None:
        self.conn.execute(
            "INSERT INTO identities (id, name, role, key_hash, active, created_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role, key_hash=excluded.key_hash, active=excluded.active",
            (ident.id, ident.name, str(ident.role), ident.key_hash, int(ident.active), time.time()),
        )
        self.conn.commit()

    @_locked
    def load_identities(self) -> list[Identity]:
        rows = self.conn.execute("SELECT * FROM identities").fetchall()
        return [Identity(id=r["id"], name=r["name"], role=Role(r["role"]), key_hash=r["key_hash"], active=bool(r["active"])) for r in rows]

    # ---- games -----------------------------------------------------------

    @_locked
    def save_game(self, game_id: str, name: str, status: str, snapshot: dict[str, Any]) -> None:
        now = time.time()
        self.conn.execute(
            "INSERT INTO games (id, name, status, snapshot, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, status=excluded.status, snapshot=excluded.snapshot, updated_at=excluded.updated_at",
            (game_id, name, status, json.dumps(snapshot), now, now),
        )
        self.conn.commit()

    @_locked
    def load_games(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM games ORDER BY created_at").fetchall()
        return [{"id": r["id"], "name": r["name"], "status": r["status"], "snapshot": json.loads(r["snapshot"])} for r in rows]

    # ---- hands -----------------------------------------------------------

    @_locked
    def save_hand(self, game_id: str, record: dict[str, Any], results: list[dict[str, Any]]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO hands (game_id, hand_number, record, completed_at) VALUES (?, ?, ?, ?)",
            (game_id, record["hand_id"], json.dumps(record), time.time()),
        )
        self.conn.executemany(
            "INSERT OR REPLACE INTO hand_results (game_id, hand_number, seat, identity_id, name, big_blind, net, vpip, pfr, "
            "bets_raises, calls, went_to_showdown, won_at_showdown, timed_out) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (game_id, record["hand_id"], r["seat"], r["identity_id"], r["name"], r["big_blind"], r["net"], r["vpip"], r["pfr"],
                 r["bets_raises"], r["calls"], r["went_to_showdown"], r["won_at_showdown"], r["timed_out"])
                for r in results
            ],
        )
        self.conn.commit()

    @_locked
    def load_hand(self, game_id: str, hand_number: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT record FROM hands WHERE game_id=? AND hand_number=?", (game_id, hand_number)).fetchone()
        return json.loads(row["record"]) if row else None

    @_locked
    def list_hands(self, game_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT record FROM hands WHERE game_id=? ORDER BY hand_number DESC LIMIT ? OFFSET ?", (game_id, limit, offset)
        ).fetchall()
        return [json.loads(r["record"]) for r in rows]

    @_locked
    def hand_results(self, game_id: str | None = None, identity_id: str | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM hand_results WHERE 1=1"
        args: list[Any] = []
        if game_id:
            q += " AND game_id=?"
            args.append(game_id)
        if identity_id:
            q += " AND identity_id=?"
            args.append(identity_id)
        return self.conn.execute(q + " ORDER BY hand_number", args).fetchall()

    # ---- chat and request log -------------------------------------------

    @_locked
    def save_chat(self, game_id: str, hand_number: int, seat: int | None, name: str, text: str, ts: float) -> None:
        self.conn.execute("INSERT INTO chat (game_id, hand_number, seat, name, text, ts) VALUES (?, ?, ?, ?, ?, ?)", (game_id, hand_number, seat, name, text, ts))
        self.conn.commit()

    @_locked
    def delete_chat(self, game_id: str) -> int:
        cur = self.conn.execute("DELETE FROM chat WHERE game_id=?", (game_id,))
        self.conn.commit()
        return cur.rowcount

    @_locked
    def log_request(self, identity_id: str | None, connector: str, game_id: str | None, request_id: str | None, operation: str, outcome: str, latency_ms: float | None, error: str | None) -> None:
        self.conn.execute(
            "INSERT INTO request_log (ts, identity_id, connector, game_id, request_id, operation, outcome, latency_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), identity_id, connector, game_id, request_id, operation, outcome, latency_ms, error),
        )
        self.conn.commit()


def hand_result_rows(game_id: str, record: dict[str, Any], seat_identity: dict[int, tuple[str, str]]) -> list[dict[str, Any]]:
    """Derive per-seat statistics rows from a completed hand record."""
    bb = record["big_blind"]
    actions = [e for e in record["events"] if e["type"] == "action"]
    timeouts = {e["seat"] for e in record["events"] if e["type"] == "timeout"}
    rows = []
    for seat_str, net in record["payoffs"].items():
        seat = int(seat_str)
        mine = [a for a in actions if a["seat"] == seat]
        pre = [a for a in mine if a["phase"] == "preflop"]
        vpip = any(a["action"] in ("call", "bet", "raise") for a in pre)
        pfr = any(a["action"] in ("bet", "raise") for a in pre)
        ident_id, name = seat_identity.get(seat, (f"seat-{seat}", f"seat-{seat}"))
        wts = seat in record["went_to_showdown"]
        rows.append({
            "seat": seat, "identity_id": ident_id, "name": name, "big_blind": bb, "net": int(net),
            "vpip": int(vpip), "pfr": int(pfr),
            "bets_raises": sum(1 for a in mine if a["action"] in ("bet", "raise")),
            "calls": sum(1 for a in mine if a["action"] == "call"),
            "went_to_showdown": int(wts), "won_at_showdown": int(wts and int(net) > 0),
            "timed_out": int(seat in timeouts),
        })
    return rows
