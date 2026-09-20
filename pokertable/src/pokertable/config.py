"""Server configuration from config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IdentityConfig:
    name: str
    key: str
    role: str = "player"


@dataclass
class ServerConfig:
    bind: str = "127.0.0.1"
    port: int = 8420
    database: str = "poker.db"
    tick_seconds: float = 0.25
    identities: list[IdentityConfig] = field(default_factory=list)

    @property
    def exposed(self) -> bool:
        return self.bind not in ("127.0.0.1", "localhost", "::1")


def load_config(path: str | Path | None) -> ServerConfig:
    if path is None or not Path(path).exists():
        return ServerConfig()
    data: dict[str, Any] = tomllib.loads(Path(path).read_text())
    server = data.get("server", {})
    idents = [IdentityConfig(**i) for i in data.get("identities", [])]
    return ServerConfig(
        bind=server.get("bind", "127.0.0.1"),
        port=int(server.get("port", 8420)),
        database=server.get("database", "poker.db"),
        tick_seconds=float(server.get("tick_seconds", 0.25)),
        identities=idents,
    )
