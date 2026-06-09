"""FastAPI application entry point"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import scheduler
from .config import get_settings
from .db import init_db

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s ...", settings.app_name)

    if settings.jwt_secret_is_insecure:
        if settings.debug:
            logger.warning(
                "JWT_SECRET is using an insecure default. Set a strong JWT_SECRET "
                "before deploying (tokens are forgeable otherwise)."
            )
        else:
            raise RuntimeError(
                "JWT_SECRET is unset or using an insecure default. Set a strong "
                "JWT_SECRET environment variable before starting in production."
            )

    init_db()
    logger.info("Database initialized")

    if settings.enable_scheduler:
        scheduler.start_scheduler()
    else:
        logger.info("Scheduler disabled (ENABLE_SCHEDULER=false)")

    yield

    if settings.enable_scheduler:
        scheduler.shutdown_scheduler()
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Tee-time availability watcher for Austin municipal golf courses",
    version="3.0.0",
    lifespan=lifespan,
)

cors_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def api_health():
    return {
        "status": "healthy",
        "scheduler": "running" if settings.enable_scheduler else "disabled",
        "timezone": settings.timezone,
    }


from .routers import auth, watches  # noqa: E402

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(watches.router, prefix="/api", tags=["watches"])

# Serve the built React frontend (after API routes are registered).
_frontend_dist = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist"
)
if os.path.exists(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
