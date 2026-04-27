"""
FastAPI application entry point.

Run with:
    uvicorn app.backend.api.main:app --reload --host 127.0.0.1 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend.api.routes.search import router as search_router
from app.backend.api.routes.cercador import router as cercador_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Pre-load the embedding model before the server starts accepting requests.

    The first load of multilingual-e5-small takes ~60-90 s on CPU from disk.
    Without pre-loading the model, the first /api/filter request would exceed
    the 30-second client-side timeout and appear to fail.
    """
    import asyncio

    from app.backend.core.encoder import load_encoder

    logger.info("Pre-loading embedding model — this takes ~60-90 s on first run …")
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, load_encoder)
        logger.info("Embedding model ready.")
    except Exception as exc:
        logger.warning(
            "Could not pre-load embedding model (%s). "
            "Semantic search will fall back to keyword matching.",
            exc,
        )
    yield  # server is now ready to accept requests


app = FastAPI(
    title="Semantic Song Search Engine",
    description="API for searching Catalan songs using semantic embeddings.",
    version="0.2.0",
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
    return {"status": "ok", "message": "Semantic Song Search Engine API v0.2"}
