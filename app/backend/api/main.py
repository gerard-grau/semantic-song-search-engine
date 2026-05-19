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
        from data_pipeline.step6_project_2d import run as run_projection
        from app.backend.core.projections import invalidate_cache as invalidate_proj
        logger.info("RECOMPUTE_2D=1 — regenerating 2D projection parquet …")
        run_projection(force=True)
        invalidate_proj()
    if _flag("RECOMPUTE_META"):
        from app.backend.core.data_loader import invalidate_cache as invalidate_loader
        from data_pipeline.step5_build_meta import run as run_metadata_snapshot
        logger.info("RECOMPUTE_META=1 — regenerating metadata snapshot …")
        run_metadata_snapshot(force=True)
        invalidate_loader()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Pre-warm everything the /filter hot path touches *before* the server
    starts accepting traffic so the first user query only pays for one
    forward pass + one matmul.

    Steps (in order):

    1. Read the cheap precomputed parquets (visible songs + 2D points) so
       the first ``/api/songs`` is instant.
    2. Build the dense visible index — the ``(N, F, D)`` cube the fast
       filter slices into. ~10-15 s of parquet + numpy work that we'd
       otherwise pay on the first query.
    3. Load the embedding model AND run a dummy ``encode_query`` to JIT
       the first forward pass. Without this, the very first real query
       takes 20-60 s on CPU (model load + transformers warm-up).
    4. Schedule the cercador index in the background — it isn't on the
       /filter path, so we don't block startup on it.
    """
    import asyncio

    from app.backend.core.cercador_index import prewarm as prewarm_cercador
    from app.backend.core.data_loader import (
        get_visible_index,
        load_visible_songs,
    )
    from app.backend.core.encoder import encode_query, load_encoder
    from app.backend.core.projections import get_all_projections_2d

    _maybe_recompute()

    loop = asyncio.get_event_loop()

    # 1. Small parquets — used by both /api/songs and the visible index.
    try:
        await loop.run_in_executor(None, load_visible_songs)
        await loop.run_in_executor(None, get_all_projections_2d)
    except Exception as exc:
        logger.warning("Could not prewarm visible-songs cache (%s).", exc)

    # 2. Dense visible index — the hot data structure /filter slices into.
    #    We wait for it; the first /api/filter must not pay this cost.
    await loop.run_in_executor(None, _safe_call, get_visible_index, "visible index")

    # 3. Embedding model + warm-up forward pass. ``load_encoder`` reads the
    #    weights; ``encode_query`` runs one inference so the kernel cache,
    #    tokenizer, and any lazy CUDA / MKL state are primed. We wait for
    #    both so the first real /api/filter only does the user's query.
    await loop.run_in_executor(None, _safe_call, load_encoder, "embedding model")
    await loop.run_in_executor(None, _safe_call, _warm_encoder, "encoder warm-up")

    # 4. Cercador index — not on the /filter path; let it finish in bg.
    loop.run_in_executor(None, _safe_call, prewarm_cercador, "cercador index")

    yield


def _warm_encoder() -> None:
    """Run one dummy encode so the model's first forward pass is paid
    before any user query hits the API. Idempotent."""
    from app.backend.core.encoder import encode_query
    encode_query("warmup")


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
