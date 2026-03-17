from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SearchMode = Literal["classic", "smart"]


class SearchResult(BaseModel):
    id: str
    title: str
    artist: str
    album: str
    year: int
    language: str
    mood_tags: list[str] = Field(default_factory=list)
    snippet: str
    match_reason: str
    similarity_score: float = Field(ge=0, le=1)


class SearchResponse(BaseModel):
    mode: SearchMode
    query: str
    total_results: int
    took_ms: int
    suggestions: list[str] = Field(default_factory=list)
    results: list[SearchResult] = Field(default_factory=list)


class SongDetail(BaseModel):
    id: str
    title: str
    artist: str
    album: str
    year: int
    language: str
    duration: str
    mood_tags: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    snippet: str
    lyrics_preview: str
    narrative: str


class Recommendation(BaseModel):
    id: str
    title: str
    artist: str
    reason: str
    similarity_score: float = Field(ge=0, le=1)
