"""Pydantic models for API request / response validation."""

from __future__ import annotations

from pydantic import BaseModel


class SongResult(BaseModel):
    id: int
    title: str
    artist: str
    album: str
    genre: str
    year: int
    lyrics_snippet: str
    score: float = 0.0


class SongDetail(BaseModel):
    id: int
    title: str
    artist: str
    album: str
    genre: str
    year: int
    lyrics_snippet: str
    full_lyrics: str
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


class Point3D(BaseModel):
    id: int
    x: float
    y: float
    z: float
    title: str
    artist: str
    genre: str


class AllSongsResponse(BaseModel):
    songs: list[SongResult]
    projections_2d: list[Point2D]
    projections_3d: list[Point3D]
    total: int


class FilterRequest(BaseModel):
    query: str
    song_ids: list[int] | None = None   # None → start from all songs


class FilterResponse(BaseModel):
    songs: list[SongResult]
    projections_2d: list[Point2D]
    projections_3d: list[Point3D]
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
