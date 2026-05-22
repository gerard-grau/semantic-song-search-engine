"""Pydantic models for API request / response validation."""

from __future__ import annotations

from pydantic import BaseModel


class SongResult(BaseModel):
    id: int
    title: str
    artist: str
    album: str = ""
    genre: str = ""
    year: int = 0
    lyrics_snippet: str = ""
    score: float = 0.0


class SongDetail(BaseModel):
    id: int
    title: str
    artist: str
    album: str = ""
    genre: str = ""
    year: int = 0
    lyrics_snippet: str = ""
    full_lyrics: str = ""
    url: str | None = None
    duration: str | None = None
    language: str | None = None


class Point2D(BaseModel):
    id: int
    x: float
    y: float
    title: str
    artist: str
    genre: str
    role: str = "neighbor"  # "focal" | "neighbor" | "previous" | "bridge"


class AllSongsResponse(BaseModel):
    songs: list[SongResult]
    projections_2d: list[Point2D]
    total: int


class FilterRequest(BaseModel):
    query: str = ""
    similar_to_id: int | None = None    # if set, similarity-to-song filter; query is ignored
    song_ids: list[int] | None = None   # None → start from all songs


class ScoreItem(BaseModel):
    """Lightweight (id, salience, rank) tuple returned by /api/filter.

    The frontend already has the full SongResult cached from /api/songs,
    so filter responses only need to ship the score updates.

    ``score`` is the *salience* — the value the scatter uses for opacity
    and colour saturation; it's already dimmed by query discriminability,
    so an uninformative query (e.g. "música") produces low scores for
    everyone. ``rank`` is the *relative position* (norm_score in [0, 1]),
    independent of discriminability, and drives point SIZE: even in a
    weak query, the relatively-best songs still render at full size so
    the user can locate them. For similar-to-song chips the two are
    identical (no discriminability concept).
    """
    id: int
    score: float
    rank: float = 0.0


class FilterResponse(BaseModel):
    songs: list[ScoreItem]
    projections_2d: list[Point2D]
    total_remaining: int
    message: str | None = None


class PreviousPosition(BaseModel):
    id: int
    x: float
    y: float


class NeighborsRequest(BaseModel):
    song_id: int
    n: int = 20
    song_ids: list[int] | None = None   # restrict neighbors to this filtered set
    previous_song_id: int | None = None
    bridge_song_ids: list[int] = []
    bridge_count: int = 5
    previous_positions: list[PreviousPosition] = []


class NeighborsResponse(BaseModel):
    songs: list[SongResult]
    projections_2d: list[Point2D]
    focal_id: int
    previous_focal_id: int | None = None
    total: int
