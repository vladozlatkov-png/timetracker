"""Browser pages. Thin: they render templates and the JavaScript talks to the same REST API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from pokertable.service.identity import Identity
from pokertable.service.stats import player_stats

from .deps import COOKIE, get_state, optional_identity
from .state import AppState

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "web" / "templates"))


def _ctx(request: Request, state: AppState, ident: Identity | None, **extra):
    return {"request": request, "ident": ident, "exposed": state.config.exposed, "bind": state.config.bind, **extra}


@router.get("/", response_class=HTMLResponse)
async def lobby(request: Request, state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)):
    games = list(state.games.values())
    return templates.TemplateResponse(request, "lobby.html", _ctx(request, state, ident, games=games))


@router.post("/login")
async def login(key: str = Form(...), next: str = Form("/")):
    resp = RedirectResponse(next or "/", status_code=303)
    resp.set_cookie(COOKIE, key, httponly=True, samesite="lax")
    return resp


@router.post("/logout")
async def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


@router.get("/table/{game_id}", response_class=HTMLResponse)
async def table(game_id: str, request: Request, state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)):
    game = state.get_game(game_id)
    return templates.TemplateResponse(request, "table.html", _ctx(request, state, ident, game=game))


@router.get("/table/{game_id}/agents", response_class=HTMLResponse)
async def agents_page(game_id: str, request: Request, state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)):
    game = state.get_game(game_id)
    return templates.TemplateResponse(request, "agents.html", _ctx(request, state, ident, game=game, agents=game.agent_panel()))


@router.get("/hands/{game_id}", response_class=HTMLResponse)
async def hands_page(game_id: str, request: Request, state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)):
    game = state.get_game(game_id)
    hands = [state.hand_record_for(game, r, ident) for r in state.repo.list_hands(game_id, 100)]
    return templates.TemplateResponse(request, "hands.html", _ctx(request, state, ident, game=game, hands=hands))


@router.get("/hands/{game_id}/{hand_number}", response_class=HTMLResponse)
async def hand_page(game_id: str, hand_number: int, request: Request, state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)):
    game = state.get_game(game_id)
    rec = state.repo.load_hand(game_id, hand_number)
    rec = state.hand_record_for(game, rec, ident) if rec else None
    return templates.TemplateResponse(request, "hand.html", _ctx(request, state, ident, game=game, hand=rec, hand_number=hand_number))


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request, game: str | None = None, state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)):
    stats = player_stats([dict(r) for r in state.repo.hand_results(game_id=game)])
    ranked = sorted(stats.values(), key=lambda s: -s["net_chips"])
    return templates.TemplateResponse(request, "stats.html", _ctx(request, state, ident, stats=ranked, game=game, games=list(state.games.values())))


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, state: AppState = Depends(get_state), ident: Identity | None = Depends(optional_identity)):
    if ident is None or not ident.can_administer:
        return templates.TemplateResponse(request, "login.html", _ctx(request, state, ident, next="/admin", message="Admin key required."))
    return templates.TemplateResponse(request, "admin.html", _ctx(request, state, ident, games=list(state.games.values()), identities=state.registry.all()))
