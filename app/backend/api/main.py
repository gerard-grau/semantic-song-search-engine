"""
FastAPI application entry point.

Run with:
    uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000

Environment flags (set before launching uvicorn):

* ``RECOMPUTE_2D=1`` — runs ``data_pipeline.run_projection`` at start-up to
  regenerate ``embedded_songs_2d.parquet`` from the embeddings parquet. This
  is the only way the API ever (re)computes the full 2D projection — normal
  start-up just reads the precomputed file.
* ``RECOMPUTE_META=1`` — also rebuilds ``songs_meta.parquet`` (the metadata
  snapshot consumed by the loaders).
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend.api.routes.cercador import router as cercador_router
from app.backend.api.routes.search import router as search_router

logger = logging.getLogger(__name__)


def _flag(name: str) -> bool:
    return os.getenv(name, "").lower() in ("1", "true", "yes", "on")


def _maybe_recompute() -> None:
    """Optionally regenerate the precomputed parquets before the server starts."""
    if _flag("RECOMPUTE_2D"):
        from app.backend.core.data_pipeline import run_projection
        from app.backend.core.projections import invalidate_cache as invalidate_proj
        logger.info("RECOMPUTE_2D=1 — regenerating 2D projection parquet …")
        run_projection()
        invalidate_proj()
    if _flag("RECOMPUTE_META"):
        from app.backend.core.data_loader import invalidate_cache as invalidate_loader
        from app.backend.core.data_pipeline import run_metadata_snapshot
        logger.info("RECOMPUTE_META=1 — regenerating metadata snapshot …")
        run_metadata_snapshot()
        invalidate_loader()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Pre-warm the embedding model and the cercador index, both off-thread so
    the API can start serving cheap endpoints (`/`, `/api/songs`) immediately.
    The first ``/api/cercador`` and ``/api/filter`` calls await whichever
    background task they need.
    """
    import asyncio

    from app.backend.core.cercador_index import prewarm as prewarm_cercador
    from app.backend.core.data_loader import load_visible_songs
    from app.backend.core.encoder import load_encoder
    from app.backend.core.projections import get_all_projections_2d

    _maybe_recompute()

    loop = asyncio.get_event_loop()

    # Lightweight: read the small precomputed parquets so the first
    # /api/songs hit is instant. Both are cached after this.
    try:
        await loop.run_in_executor(None, load_visible_songs)
        await loop.run_in_executor(None, get_all_projections_2d)
    except Exception as exc:
        logger.warning("Could not prewarm visible-songs cache (%s).", exc)

    # Heavy work — schedule on the executor and let it run in the background.
    # run_in_executor returns a Future that's already scheduled; no create_task needed.
    loop.run_in_executor(None, _safe_call, load_encoder, "embedding model")
    loop.run_in_executor(None, _safe_call, prewarm_cercador, "cercador index")

    yield


def _safe_call(fn, label: str) -> None:
    try:
        logger.info("Pre-loading %s …", label)
        fn()
        logger.info("%s ready.", label.capitalize())
    except Exception as exc:
        logger.warning("Could not pre-load %s (%s).", label, exc)


app = FastAPI(
    title="Semantic Song Search Engine",
    description="API for searching Catalan songs using semantic embeddings.",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(cercador_router)


@app.get("/")
def root():
    return {"status": "ok", "message": "Semantic Song Search Engine API v0.3"}
