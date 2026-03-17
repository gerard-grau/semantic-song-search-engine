from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..mock_data import get_recommendations, get_song
from ..schemas import Recommendation, SongDetail

router = APIRouter(prefix="/songs", tags=["songs"])


@router.get("/{song_id}", response_model=SongDetail)
def song_detail(song_id: str) -> SongDetail:
    song = get_song(song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.get("/{song_id}/recommendations", response_model=list[Recommendation])
def song_recommendations(song_id: str) -> list[Recommendation]:
    song = get_song(song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return get_recommendations(song_id)
