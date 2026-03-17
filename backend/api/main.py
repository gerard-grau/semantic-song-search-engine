from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.search import router as search_router
from .routes.songs import router as songs_router

app = FastAPI(
    title="Semantic Song Search MVP API",
    description="Mock API for the Viasona hybrid-search stakeholder demo.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(songs_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Semantic Song Search MVP API"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
