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

A second endpoint, ``/api/cercador/suggestions``, runs the embedding
model over the query to surface qualitative-description matches and
extra lyrics hits. It's split off so the frontend can fire it on a
slower trigger (per-space / 2 s idle) than the per-keystroke keyword
search above.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.backend.core.cercador_index import derive_correction, get_index
from app.backend.core.data_loader import get_visible_index
from app.backend.core.embeddings import compute_cercador_suggestions

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


def _suggestion_result(song: dict, score: float) -> dict:
    """Result row for both the Sugerències section and the lyrics-extra
    appended to the Lletres section.

    ``score`` is the raw embedding cosine; clamped to [0, 1] before
    serialising so the frontend can render it as a "% match" without a
    second pass. Negative cosines collapse to 0 — a song that's actively
    *anti-aligned* with the query isn't a useful suggestion.
    """
    return {
        "id":             song["id"],
        "title":          song.get("title", ""),
        "artist":         song.get("artist", ""),
        "lyrics_snippet": song.get("lyrics_snippet", ""),
        "genre":          song.get("genre", ""),
        "url":            song.get("url", ""),
        "score":          round(max(0.0, min(1.0, float(score))), 4),
    }


def _parse_exclude_ids(raw: str) -> set[int]:
    out: set[int] = set()
    if not raw:
        return out
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def _parse_exclude_names(raw: str) -> set[str]:
    """``"Manel,Sopa de Cabra"`` → ``{"Manel", "Sopa de Cabra"}``.

    Names are passed verbatim from the frontend (the lexical Grups column
    already renders them with the canonical capitalisation from grups.csv),
    so we strip but don't normalise — the embedding side uses the same
    ``s["artist"]`` string the songs table carries, which matches.
    """
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


@router.get("/cercador/suggestions")
def cercador_suggestions(q: str = "", exclude_ids: str = "", exclude_groups: str = ""):
    """Embedding-based companion to ``/api/cercador``.

    Response shape::

        {
          "suggestions":  [ { id, title, artist, lyrics_snippet,
                              genre, url, score }, … ],   # top 4
          "lyrics_extra": [ { id, title, artist, lyrics_snippet,
                              genre, url, score }, … ],   # top 2
          "group_extra":  null | { …grup_result fields…, score },  # top 0–1
        }

    ``score`` is cosine in [0, 1]. ``exclude_ids`` excludes songs already
    shown in the Lletres column; ``exclude_groups`` (comma-separated artist
    names) excludes groups already shown in the Grups column. Both keep
    the embedding extras strictly *new* hits.
    """
    q = q.strip()
    if not q:
        return {"suggestions": [], "lyrics_extra": [], "group_extra": None}

    excluded_ids   = _parse_exclude_ids(exclude_ids)
    excluded_names = _parse_exclude_names(exclude_groups)

    try:
        index = get_visible_index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Suggestions: visible index unavailable (%s)", exc)
        return {"suggestions": [], "lyrics_extra": [], "group_extra": None}

    scored = compute_cercador_suggestions(
        query_text=q,
        index=index,
        exclude_ids=excluded_ids,
        exclude_artist_names=excluded_names,
    )
    songs = index["songs"]

    group_extra = None
    if scored["group_extra"]:
        artist_name, score = scored["group_extra"][0]
        grup_record = get_index().find_grup_by_name(artist_name)
        # If we have an embedding-strong artist but no grups.csv record for
        # them, surface a minimal stub instead of dropping the suggestion
        # entirely — the user still wants to see "we found this artist".
        if grup_record is not None:
            group_extra = {
                **_grup_result(grup_record),
                "score": round(max(0.0, min(1.0, float(score))), 4),
            }
        else:
            group_extra = {
                "id":           0,
                "name":         artist_name,
                "song_count":   0,
                "viasona_link": "",
                "foto":         "",
                "municipi":     "",
                "regio":        "",
                "genres":       [],
                "score":        round(max(0.0, min(1.0, float(score))), 4),
            }

    return {
        "suggestions": [
            _suggestion_result(songs[i], score)
            for i, score in scored["suggestions"]
        ],
        "lyrics_extra": [
            _suggestion_result(songs[i], score)
            for i, score in scored["lyrics_extra"]
        ],
        "group_extra": group_extra,
    }
