from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from pokertable.service.identity import Identity

from .state import AppState

COOKIE = "pt_key"


def get_state(request: Request) -> AppState:
    return request.app.state.pt


def extract_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE)


def optional_identity(request: Request, state: AppState = Depends(get_state)) -> Identity | None:
    return state.registry.authenticate(extract_key(request))


def current_identity(ident: Identity | None = Depends(optional_identity)) -> Identity:
    if ident is None:
        raise HTTPException(401, {"error": "unauthenticated", "message": "missing or invalid API key"})
    return ident


def admin_identity(ident: Identity = Depends(current_identity)) -> Identity:
    if not ident.can_administer:
        raise HTTPException(403, {"error": "forbidden", "message": "admin role required"})
    return ident
