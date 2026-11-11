"""Application factory. Run: uvicorn app.main:create_app --factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, load_settings
from app.core.constants import REQUEST_ID_HEADER
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.protection import BodySizeLimitMiddleware, FixedWindowLimiter
from app.core.security import SecurityHeadersMiddleware
from app.database.session import build_engine, build_sessionmaker
from app.health.router import router as health_router
from app.integrations.botcheck import BotVerifier, build_bot_verifier
from app.integrations.email import EmailSender, build_email_sender
from app.integrations.storage import Storage, build_storage


def create_app(
    settings: Settings | None = None,
    *,
    storage: Storage | None = None,
    email_sender: EmailSender | None = None,
    bot_verifier: BotVerifier | None = None,
) -> FastAPI:
    """Adapters are injectable so tests (and later phases) can swap storage/email/bot-check."""
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logging.getLogger("app").info(
            "starting", extra={"app_env": settings.app_env, "version": settings.app_version}
        )
        yield
        engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        # API docs are not exposed in production.
        docs_url=None if settings.is_hardened else "/docs",
        redoc_url=None if settings.is_hardened else "/redoc",
        openapi_url=None if settings.is_hardened else "/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    app.state.storage = storage or build_storage(settings)
    app.state.email_sender = email_sender or build_email_sender(settings)
    app.state.bot_verifier = bot_verifier or build_bot_verifier(settings)
    app.state.rate_limiter = FixedWindowLimiter()

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    if not settings.is_hardened:
        # Only where the docs are exposed: the site root opens the Swagger UI.
        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/docs")

    # Added first = innermost. RequestContext is outermost so every response gets a request id.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Bot-Token",
            "X-Lookup-Token",
            REQUEST_ID_HEADER,
        ],
        expose_headers=[REQUEST_ID_HEADER, "Idempotent-Replay", "Retry-After"],
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_hardened)
    app.add_middleware(RequestContextMiddleware)
    return app
