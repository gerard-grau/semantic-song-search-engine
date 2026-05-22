"""API routes for song search, filtering, and detail retrieval."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.backend.api.schemas import (
    AllSongsResponse,
    FilterRequest,
    FilterResponse,
    NeighborsRequest,
    NeighborsResponse,
    Point2D,
    ScoreItem,
    SongDetail,
    SongResult,
)
from app.backend.core.data_loader import (
    attach_embeddings,
    attach_genre_profiles,
    get_song_by_id,
    get_songs_by_ids,
    get_visible_index,
    load_visible_songs,
)
from app.backend.core.embeddings import (
    build_neighborhood,
    filter_by_similarity_fast,
    filter_embeddings_fast,
)
from app.backend.core.projections import (
    compute_neighborhood_2d,
    get_all_projections_2d,
)

router = APIRouter(prefix="/api")


def _to_result(song: dict) -> SongResult:
    return SongResult(
        id=song["id"],
        title=song.get("title", ""),
        artist=song.get("artist", ""),
        album=song.get("album", ""),
        genre=song.get("genre", ""),
        year=song.get("year", 0),
        lyrics_snippet=song.get("lyrics_snippet", ""),
        score=song.get("score", 0.0),
    )


@router.get("/songs", response_model=AllSongsResponse)
def get_all_songs():
    """Return visible songs + their pre-computed 2D coordinates."""
    songs = load_visible_songs()
    return AllSongsResponse(
        songs=[_to_result(s) for s in songs],
        projections_2d=[Point2D(**p) for p in get_all_projections_2d()],
        total=len(songs),
    )


@router.post("/filter", response_model=FilterResponse)
def filter_songs(body: FilterRequest):
    """Progressive filter — text query OR similar-to-song mode.

    When ``similar_to_id`` is set the request is treated as a chip-style
    "songs similar to X" filter; the text ``query`` is ignored in that mode.
    Scoring runs on the dense pre-built visible index (built lazily on
    first call) so each request is one matmul on a row slice rather than a
    fresh (n, F, D) allocation.
    """
    index = get_visible_index()
    songs = index["songs"]

    if body.similar_to_id is not None:
        scored = filter_by_similarity_fast(
            focal_id=body.similar_to_id,
            song_ids=body.song_ids,
            index=index,
        )
        # Song-to-song similarity has no discriminability concept — every
        # survivor passed the percentile, so salience = rank = score.
        items = [
            ScoreItem(id=songs[idx]["id"], score=s, rank=s) for idx, s in scored
        ]
    else:
        scored = filter_embeddings_fast(
            query_text=body.query,
            song_ids=body.song_ids,
            index=index,
        )
        # Text-query path returns (idx, salience, rank).
        items = [
            ScoreItem(id=songs[idx]["id"], score=sal, rank=rk)
            for idx, sal, rk in scored
        ]

    n = len(items)
    message = f"Explora les {n} cançons per tu" if n <= 5 else None

    return FilterResponse(
        songs=items,
        projections_2d=[],
        total_remaining=n,
        message=message,
    )


@router.post("/neighbors", response_model=NeighborsResponse)
def get_song_neighbors(body: NeighborsRequest):
    """Return the neighborhood of a focal song for graph-style exploration."""
    all_songs = (
        get_songs_by_ids(body.song_ids)
        if body.song_ids is not None
        else load_visible_songs()
    )
    attach_embeddings(all_songs)
    attach_genre_profiles(all_songs)

    neighborhood = build_neighborhood(
        focal_id=body.song_id,
        all_songs=all_songs,
        n=body.n,
        previous_song_id=body.previous_song_id,
        bridge_song_ids=body.bridge_song_ids or [],
        bridge_count=body.bridge_count,
    )
    if not neighborhood:
        raise HTTPException(status_code=404, detail=f"Song {body.song_id} not found")

    prev_pos = (
        {p.id: (p.x, p.y) for p in body.previous_positions}
        if body.previous_positions
        else None
    )
    proj_2d = compute_neighborhood_2d(
        neighborhood,
        focal_id=body.song_id,
        previous_song_id=body.previous_song_id,
        previous_positions=prev_pos,
    )
    return NeighborsResponse(
        songs=[_to_result(s) for s in neighborhood],
        projections_2d=[Point2D(**p) for p in proj_2d],
        focal_id=body.song_id,
        previous_focal_id=body.previous_song_id,
        total=len(neighborhood),
    )


@router.get("/songs/{song_id}", response_model=SongDetail)
def get_song(song_id: int):
    """Full detail for a single song (used by the popup)."""
    song = get_song_by_id(song_id)
    if song is None:
        raise HTTPException(status_code=404, detail=f"Song {song_id} not found")
    return SongDetail(
        id=song["id"],
        title=song.get("title", ""),
        artist=song.get("artist", ""),
        album=song.get("album", ""),
        genre=song.get("genre", ""),
        year=song.get("year", 0),
        lyrics_snippet=song.get("lyrics_snippet", ""),
        full_lyrics=song.get("full_lyrics", ""),
        url=song.get("url"),
        duration=song.get("duration"),
        language=song.get("language"),
    )
