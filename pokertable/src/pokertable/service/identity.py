"""Identities, roles and API keys. Keys are stored hashed; the registry is the only place that sees raw keys."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    PLAYER = "player"
    OBSERVER = "observer"
    ANALYST = "analyst"


@dataclass
class Identity:
    id: str
    name: str
    role: Role
    key_hash: str
    active: bool = True

    @property
    def can_play(self) -> bool:
        return self.role in (Role.PLAYER, Role.ADMIN)

    @property
    def can_administer(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def can_analyse(self) -> bool:
        return self.role in (Role.ANALYST, Role.ADMIN)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class IdentityRegistry:
    def __init__(self) -> None:
        self._by_hash: dict[str, Identity] = {}
        self._by_id: dict[str, Identity] = {}

    def add(self, name: str, role: Role | str, key: str | None = None, id: str | None = None) -> tuple[Identity, str]:
        key = key or secrets.token_urlsafe(24)
        ident = Identity(id=id or name, name=name, role=Role(role), key_hash=hash_key(key))
        if ident.id in self._by_id and self._by_id[ident.id].key_hash != ident.key_hash:
            # replace the key for an existing identity
            old = self._by_id[ident.id]
            self._by_hash.pop(old.key_hash, None)
        self._by_hash[ident.key_hash] = ident
        self._by_id[ident.id] = ident
        return ident, key

    def load(self, ident: Identity) -> None:
        self._by_hash[ident.key_hash] = ident
        self._by_id[ident.id] = ident

    def authenticate(self, key: str | None) -> Identity | None:
        if not key:
            return None
        ident = self._by_hash.get(hash_key(key))
        return ident if ident and ident.active else None

    def get(self, ident_id: str) -> Identity | None:
        return self._by_id.get(ident_id)

    def revoke(self, ident_id: str) -> bool:
        ident = self._by_id.get(ident_id)
        if not ident:
            return False
        ident.active = False
        return True

    def all(self) -> list[Identity]:
        return list(self._by_id.values())
