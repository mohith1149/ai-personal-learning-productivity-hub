"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

import truststore

# Use the Windows/OS certificate store for all outbound TLS (GitHub, Anthropic, SMTP).
# Required on machines where antivirus/proxy re-signs HTTPS traffic.
truststore.inject_into_ssl()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import engine  # noqa: E402
from app.routers import api_router  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hub")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("Starting %s (env=%s, scheduler=%s)", settings.app_name, settings.environment,
             settings.scheduler_mode)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok", "version": app.version}

    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
