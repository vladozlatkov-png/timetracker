"""FastAPI application factory and CLI entry point."""

from __future__ import annotations

import argparse
import contextlib
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from pokertable import __version__
from pokertable.config import ServerConfig, load_config
from pokertable.db import Repository
from pokertable.service import ServiceError

from . import routes, web
from .state import AppState

STATIC = Path(__file__).resolve().parent.parent / "web" / "static"


def create_app(config: ServerConfig | None = None, repo: Repository | None = None) -> FastAPI:
    config = config or ServerConfig()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        state = AppState(config, repo)
        app.state.pt = state
        await state.start()
        try:
            yield
        finally:
            await state.stop()

    app = FastAPI(title="Independent AI Poker Table", version=__version__, lifespan=lifespan)
    app.include_router(routes.router)
    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return JSONResponse(exc.as_dict(), status_code=exc.status)

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Run the poker table service")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--bind")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.bind:
        cfg.bind = args.bind
    if args.port:
        cfg.port = args.port
    if cfg.exposed:
        print(f"WARNING: listening on {cfg.bind}:{cfg.port}. The table is reachable beyond this machine.")
    uvicorn.run(create_app(cfg), host=cfg.bind, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
