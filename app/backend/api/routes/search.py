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
    Point3D,
    SongDetail,
    SongResult,
)
from app.backend.core.data_loader import get_song_by_id, get_songs_by_ids, load_all_songs
from app.backend.core.embeddings import build_neighborhood, filter_embeddings
from app.backend.core.projections import (
    compute_neighborhood_2d,
    compute_tsne_2d,
    compute_tsne_3d,
    get_all_projections_2d,
    get_all_projections_3d,
)

router = APIRouter(prefix="/api")


def _to_result(song: dict) -> SongResult:
    return SongResult(
        id=song["id"],
        title=song["title"],
        artist=song["artist"],
        album=song["album"],
        genre=song["genre"],
        year=song["year"],
        lyrics_snippet=song["lyrics_snippet"],
        score=song.get("score", 0.0),
    )


# ------------------------------------------------------------------
# GET /api/songs  –  initial load / reset
# ------------------------------------------------------------------
@router.get("/songs", response_model=AllSongsResponse)
def get_all_songs():
    """
    Return all songs with cached full-dataset t-SNE projections.
    Used on initial page load and when the user presses "Reset".
    """
    songs = load_all_songs()
    return AllSongsResponse(
        songs=[_to_result(s) for s in songs],
        projections_2d=[Point2D(**p) for p in get_all_projections_2d()],
        projections_3d=[Point3D(**p) for p in get_all_projections_3d()],
        total=len(songs),
    )


# ------------------------------------------------------------------
# POST /api/filter  –  progressive filtering
# ------------------------------------------------------------------
@router.post("/filter", response_model=FilterResponse)
def filter_songs(body: FilterRequest):
    """
    Progressive filter.

    1. If song_ids is provided, restrict to those songs; otherwise use all.
    2. Apply filter_embeddings(query, songs) → survivors with scores.
    3. Re-compute t-SNE 2D & 3D on the survivors.
    4. If ≤ 5 survivors → include a special message.
    """
    if body.song_ids is not None:
        songs = get_songs_by_ids(body.song_ids)
    else:
        songs = load_all_songs()

    survivors = filter_embeddings(query_text=body.query, songs=songs)
    n = len(survivors)

    # Compute fresh t-SNE on the surviving subset
    proj_2d = compute_tsne_2d(survivors)
    proj_3d = compute_tsne_3d(survivors)

    message = None
    if n <= 5:
        message = f"Explora les {n} cançons per tu"

    return FilterResponse(
        songs=[_to_result(s) for s in survivors],
        projections_2d=[Point2D(**p) for p in proj_2d],
        projections_3d=[Point3D(**p) for p in proj_3d],
        total_remaining=n,
        message=message,
    )


# ------------------------------------------------------------------
# POST /api/neighbors  –  neighborhood exploration
# ------------------------------------------------------------------
@router.post("/neighbors", response_model=NeighborsResponse)
def get_song_neighbors(body: NeighborsRequest):
    """
    Return the neighborhood of a focal song for graph-style exploration.

    - Finds N nearest neighbors by cosine similarity.
    - Always includes the previous focal song (role="previous").
    - Injects the most similar bridge songs from the previous neighborhood
      (role="bridge") to anchor the layout and provide visual continuity.
    - Projects with metric MDS on cosine distances; focal is always centred.
    - Rotates the plane so the previous focal appears in the travel direction.
    """
    all_songs = (
        get_songs_by_ids(body.song_ids)
        if body.song_ids is not None
        else load_all_songs()
    )
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

    # Build previous-position lookup for angle-preserving rotation
    prev_pos: dict[int, tuple[float, float]] | None = None
    if body.previous_positions:
        prev_pos = {p.id: (p.x, p.y) for p in body.previous_positions}

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


# ------------------------------------------------------------------
# GET /api/songs/{song_id}  –  song detail
# ------------------------------------------------------------------
@router.get("/songs/{song_id}", response_model=SongDetail)
def get_song(song_id: int):
    """Return full detail for a single song (used by the popup)."""
    song = get_song_by_id(song_id)
    if song is None:
        raise HTTPException(status_code=404, detail=f"Song {song_id} not found")
    return SongDetail(
        id=song["id"],
        title=song["title"],
        artist=song["artist"],
        album=song["album"],
        genre=song["genre"],
        year=song["year"],
        lyrics_snippet=song["lyrics_snippet"],
        full_lyrics=song.get("full_lyrics", ""),
        url=song.get("url"),
        duration=song.get("duration"),
        language=song.get("language"),
    )
