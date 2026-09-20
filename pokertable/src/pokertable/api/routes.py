"""REST contract. Every endpoint resolves an identity and goes through the service layer."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from pokertable.service import GameConfig, ServiceError
from pokertable.service.identity import Identity
from pokertable.service.stats import player_stats

from .deps import admin_identity, current_identity, get_state, optional_identity
from .exports import hand_text, results_csv
from .state import AppState

router = APIRouter(prefix="/v1")


def _err(e: ServiceError) -> HTTPException:
    return HTTPException(e.status, e.as_dict())


# ---- models ----------------------------------------------------------------

class JoinRequest(BaseModel):
    seat: int | None = None
    connector: str = "rest"


class ActionRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    hand_id: int | None = None
    turn_token: str | None = None
    action: str
    amount: int | None = None


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=280)


class CreateGameRequest(BaseModel):
    game_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    name: str = "Table"
    small_blind: int = 5
    big_blind: int = 10
    starting_stack: int = 1000
    max_seats: int = Field(default=6, ge=2, le=9)
    decision_seconds: float = 90.0
    hand_limit: int = 100
    hand_pause_seconds: float = 3.0
    reveal_all_after_game: bool = True
    open_join: bool = True
    auto_rebuy: bool = False


class AdminSeatRequest(BaseModel):
    identity_id: str
    seat: int | None = None
    stack: int | None = None


class CreateIdentityRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    role: str = "player"


# ---- discovery and seating -------------------------------------------------

@router.get("/me")
async def me(ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    seats = {gid: g.seat_of(ident.id).seat for gid, g in state.games.items() if g.seat_of(ident.id)}
    return {"id": ident.id, "name": ident.name, "role": ident.role, "seats": seats}


@router.get("/games")
async def list_games(state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)) -> list[dict[str, Any]]:
    out = []
    for g in state.games.values():
        out.append({
            "game_id": g.config.game_id, "name": g.config.name, "status": g.status,
            "blinds": {"small": g.config.small_blind, "big": g.config.big_blind},
            "seats_taken": len(g.seats), "max_seats": g.config.max_seats, "hand_number": g.hand_number,
            "hand_limit": g.config.hand_limit, "open_join": g.config.open_join,
            "my_seat": (g.seat_of(ident.id).seat if ident and g.seat_of(ident.id) else None),
        })
    return out


@router.post("/games/{game_id}/seats/join")
async def join_game(game_id: str, body: JoinRequest, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    if not game.config.open_join and not game.seat_of(ident.id):
        raise HTTPException(403, {"error": "closed_table", "message": "seats are assigned by the administrator"})
    try:
        seat = game.add_seat(ident, body.seat, connector=body.connector)
    except ServiceError as e:
        raise _err(e)
    state.save_game(game)
    return {"seat": seat.seat, "stack": seat.stack, "game_status": game.status}


# ---- play ------------------------------------------------------------------

@router.get("/games/{game_id}/observation")
async def observation(game_id: str, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    _touch(game, ident)
    return game.observation(ident)


@router.get("/games/{game_id}/wait")
async def wait_for_turn(game_id: str, timeout: float = Query(default=30.0, ge=0, le=120), ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    """Long-poll: returns as soon as it is the caller's turn, the hand or game state changes materially, or the timeout elapses."""
    game = state.get_game(game_id)
    _touch(game, ident)
    deadline = time.monotonic() + timeout
    seat = game.seat_of(ident.id)
    hand_no = game.hand_number
    while True:
        obs = game.observation(ident)
        if obs["my_turn"] or game.status != "running":
            return obs
        if seat is None or game.hand_number != hand_no:
            return obs
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return obs
        await state.wait_for_change(game_id, game.version, remaining)


@router.get("/games/{game_id}/legal-actions")
async def legal_actions(game_id: str, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    try:
        return game.legal_actions(ident)
    except ServiceError as e:
        raise _err(e)


@router.post("/games/{game_id}/actions")
async def submit_action(game_id: str, body: ActionRequest, request: Request, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    t0 = time.perf_counter()
    connector = request.headers.get("x-connector") or ""
    try:
        result = game.submit_action(ident, body.model_dump())
    except ServiceError as e:
        state.repo.log_request(ident.id, connector or "rest", game_id, body.request_id, "submit_action", e.code, (time.perf_counter() - t0) * 1000, e.message)
        raise _err(e)
    seat = game.seat_of(ident.id)
    if seat is not None:
        seat.last_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if connector:
            seat.connector = connector
    state.repo.log_request(ident.id, connector or "rest", game_id, body.request_id, "submit_action", "accepted", (time.perf_counter() - t0) * 1000, None)
    return result


@router.post("/games/{game_id}/chat")
async def chat(game_id: str, body: ChatRequest, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    try:
        msg = game.say(ident, body.text)
    except ServiceError as e:
        raise _err(e)
    state.repo.save_chat(game_id, msg.hand_number, msg.seat, msg.name, msg.text, msg.ts)
    return {"ok": True}


# ---- results ---------------------------------------------------------------

@router.get("/games/{game_id}/hands")
async def hand_history(game_id: str, limit: int = Query(default=20, le=200), offset: int = 0, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    game = state.get_game(game_id)
    return [state.hand_record_for(game, r, ident) for r in state.repo.list_hands(game_id, limit, offset)]


@router.get("/games/{game_id}/hands/{hand_number}")
async def hand_result(game_id: str, hand_number: int, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    rec = state.repo.load_hand(game_id, hand_number)
    if rec is None:
        raise HTTPException(404, {"error": "not_found", "message": "no such completed hand"})
    return state.hand_record_for(game, rec, ident)


@router.get("/games/{game_id}/stats")
async def game_stats(game_id: str, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    state.get_game(game_id)
    return player_stats([dict(r) for r in state.repo.hand_results(game_id=game_id)])


@router.get("/players/{player_id}/stats")
async def player_statistics(player_id: str, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    stats = player_stats([dict(r) for r in state.repo.hand_results(identity_id=player_id)])
    return stats.get(player_id, {"identity_id": player_id, "hands": 0})


@router.get("/games/{game_id}/export")
async def export(game_id: str, format: str = Query(default="json", pattern="^(json|csv|txt)$"), ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> Response:
    game = state.get_game(game_id)
    if format == "csv":
        return PlainTextResponse(results_csv([dict(r) for r in state.repo.hand_results(game_id=game_id)]), media_type="text/csv")
    records = [state.hand_record_for(game, r, ident) for r in reversed(state.repo.list_hands(game_id, limit=100000))]
    if format == "txt":
        return PlainTextResponse("\n".join(hand_text(game.config.name, r) for r in records))
    return Response(json.dumps(records, indent=1), media_type="application/json")


@router.get("/games/{game_id}/agents")
async def agents(game_id: str, ident: Identity = Depends(current_identity), state: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    return state.get_game(game_id).agent_panel()


@router.get("/games/{game_id}/stream")
async def stream(game_id: str, request: Request, state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)) -> StreamingResponse:
    """Server-Sent Events. Sends the caller's filtered observation whenever the table changes."""
    state.get_game(game_id)

    async def gen():
        version = -1
        while not await request.is_disconnected():
            game = state.games[game_id]
            if game.version != version:
                version = game.version
                obs = game.observation(ident) if ident else game.public_state()
                yield f"event: state\ndata: {json.dumps(obs)}\n\n"
            changed = await state.wait_for_change(game_id, version, 15.0)
            if not changed:
                yield ": keepalive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- administration --------------------------------------------------------

@router.post("/admin/games", status_code=201)
async def create_game(body: CreateGameRequest, ident: Identity = Depends(admin_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    try:
        game = state.create_game(GameConfig(**body.model_dump()))
    except ServiceError as e:
        raise _err(e)
    return {"game_id": game.config.game_id, "status": game.status}


@router.post("/admin/games/{game_id}/seats")
async def admin_seat(game_id: str, body: AdminSeatRequest, ident: Identity = Depends(admin_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    target = state.registry.get(body.identity_id)
    if target is None:
        raise HTTPException(404, {"error": "not_found", "message": "no such identity"})
    try:
        seat = game.add_seat(target, body.seat, body.stack)
    except ServiceError as e:
        raise _err(e)
    state.save_game(game)
    return {"seat": seat.seat, "identity_id": target.id}


@router.delete("/admin/games/{game_id}/seats/{seat}")
async def admin_unseat(game_id: str, seat: int, ident: Identity = Depends(admin_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    try:
        game.remove_seat(seat)
    except ServiceError as e:
        raise _err(e)
    state.save_game(game)
    return {"ok": True}


@router.post("/admin/games/{game_id}/{command}")
async def admin_command(game_id: str, command: str, ident: Identity = Depends(admin_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    game = state.get_game(game_id)
    try:
        if command in ("start", "resume"):
            game.start()
        elif command == "pause":
            game.pause()
        elif command == "stop":
            game.stop()
        elif command == "clear-chat":
            game.chat.clear()
            state.repo.delete_chat(game_id)
        else:
            raise HTTPException(404, {"error": "not_found", "message": f"unknown command {command}"})
    except ServiceError as e:
        raise _err(e)
    state.save_game(game)
    return {"game_id": game_id, "status": game.status}


@router.get("/admin/identities")
async def list_identities(ident: Identity = Depends(admin_identity), state: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    return [{"id": i.id, "name": i.name, "role": i.role, "active": i.active} for i in state.registry.all()]


@router.post("/admin/identities", status_code=201)
async def create_identity(body: CreateIdentityRequest, ident: Identity = Depends(admin_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    if state.registry.get(body.name):
        raise HTTPException(409, {"error": "exists", "message": "identity exists; revoke it first to rotate the key"})
    try:
        new, key = state.registry.add(body.name, body.role)
    except ValueError:
        raise HTTPException(400, {"error": "bad_role", "message": "role must be admin, player, observer or analyst"})
    state.repo.save_identity(new)
    return {"id": new.id, "name": new.name, "role": new.role, "api_key": key}


@router.delete("/admin/identities/{identity_id}")
async def revoke_identity(identity_id: str, ident: Identity = Depends(admin_identity), state: AppState = Depends(get_state)) -> dict[str, Any]:
    if identity_id == ident.id:
        raise HTTPException(400, {"error": "self_revoke", "message": "cannot revoke your own key"})
    if not state.registry.revoke(identity_id):
        raise HTTPException(404, {"error": "not_found", "message": "no such identity"})
    state.repo.save_identity(state.registry.get(identity_id))  # type: ignore[arg-type]
    return {"ok": True}


def _touch(game, ident: Identity) -> None:
    seat = game.seat_of(ident.id)
    if seat is not None:
        seat.last_request_at = time.time()
