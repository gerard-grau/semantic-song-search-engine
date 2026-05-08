"""
API route for the Viasona-style instant search (cercador).

Backed by:
  * :mod:`app.backend.core.parser2` — query expansion / fuzzy correction
  * :mod:`app.backend.core.cercador_index` — inverted indices over the
    real CSVs (cancons, grups, noticies). Built once on first request.

Response shape (kept compatible with CercadorPage.jsx):

    {
      "grups":      [ { id, name, song_count, viasona_link, foto, municipi, regio, genres }, … ],
      "cancons":    [ { id, title, artist, lyrics_snippet, genre, url }, … ],
      "noticies":   [ { id, title, snippet, date, viasona_link }, … ],
      "correction": null | { corrected, suggestions }
    }
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.backend.core.cercador_index import derive_correction, get_index

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _song_result(song: dict) -> dict:
    return {
        "id":             song["id"],
        "title":          song.get("title", ""),
        "artist":         song.get("artist", ""),
        "lyrics_snippet": song.get("lyrics_snippet", ""),
        "genre":          song.get("genre", ""),
        "url":            song.get("url", ""),
    }


def _grup_result(grup: dict) -> dict:
    return {
        "id":           grup["id"],
        "name":         grup["name"],
        "song_count":   grup.get("song_count", 0),
        "viasona_link": grup.get("viasona_link", ""),
        "foto":         grup.get("foto", ""),
        "municipi":     grup.get("municipi", ""),
        "regio":        grup.get("regio", ""),
        "genres":       grup.get("genres", []),
    }


def _noticia_result(noticia: dict) -> dict:
    return {
        "id":           noticia["id"],
        "title":        noticia["title"],
        "snippet":      noticia.get("snippet", ""),
        "date":         noticia.get("date", ""),
        "viasona_link": noticia.get("viasona_link", ""),
    }


@router.get("/cercador")
def cercador_search(q: str = ""):
    q = q.strip()
    if not q:
        return {"grups": [], "cancons": [], "noticies": [], "correction": None}

    index = get_index()
    hits = index.search(q)

    correction = derive_correction(q, hits["parsed"], index)

    return {
        "grups":      [_grup_result(g)    for g in hits["grups"]],
        "cancons":    [_song_result(s)    for s in hits["cancons"]],
        "noticies":   [_noticia_result(n) for n in hits["noticies"]],
        "correction": correction,
    }
