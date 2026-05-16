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

import numpy as np
from fastapi import APIRouter

from app.backend.core.cercador_index import derive_correction, get_index
from app.backend.core.data_loader import get_visible_index
from app.backend.core.embeddings import (
    compute_cercador_suggestions,
    compute_group_extra,
)

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
def cercador_suggestions(
    q: str = "",
    exclude_ids: str = "",
    exclude_groups: str = "",
    artist_filter: str = "",
):
    """Embedding-based companion to ``/api/cercador``.

    Response shape::

        {
          "suggestions":  [ { id, title, artist, lyrics_snippet,
                              genre, url, score }, … ],   # top 5
          "lyrics_extra": [ { id, title, artist, lyrics_snippet,
                              genre, url, score }, … ],   # top 3
          "group_extra":  null | { …grup_result fields…, score },  # 0–1
        }

    When a Docker Qdrant instance is running and indexed (via
    ``ml/embeddings/index_qdrant_docker.py``), song results come from:

      * ``suggestions``  — qualitative_description collection (mood/theme)
      * ``lyrics_extra`` — lyrics-chunks collection (chunked-lyrics recall)

    When Qdrant is unavailable the endpoint falls back to the dense visible
    index matmul (top-5000 songs only, same as the old behaviour).

    ``artist_filter`` (optional) narrows both Qdrant collections to songs by
    that exact artist name via a Qdrant payload filter.

    ``exclude_ids`` / ``exclude_groups`` keep embedding extras strictly new.
    """
    q = q.strip()
    artist_filter = artist_filter.strip() or None

    if not q:
        return {"suggestions": [], "lyrics_extra": [], "group_extra": None}

    excluded_ids   = _parse_exclude_ids(exclude_ids)
    excluded_names = _parse_exclude_names(exclude_groups)

    # ── Qdrant path ────────────────────────────────────────────────────────────
    qdrant_result = _qdrant_suggestions(q, excluded_ids, excluded_names, artist_filter)
    if qdrant_result is not None:
        return qdrant_result

    # ── Matrix fallback (existing BGE-M3 cube, top-5000 only) ─────────────────
    # artist_filter is silently ignored in fallback mode because the matrix
    # index has no payload — the user will see results across all artists.
    return _matrix_suggestions(q, excluded_ids, excluded_names)


# ── Qdrant path helpers ────────────────────────────────────────────────────────

def _qdrant_suggestions(
    q: str,
    excluded_ids: set[int],
    excluded_names: set[str],
    artist_filter: str | None,
) -> dict | None:
    """Try Qdrant; return a complete response dict or None if unavailable."""
    from app.backend.core import qdrant_search  # lazy import — avoids startup cost

    if not qdrant_search.is_available():
        return None

    from app.backend.core.encoder import encode_query

    try:
        q_arr = np.asarray(encode_query(q), dtype=np.float32)
        q_norm = float(np.linalg.norm(q_arr))
        if q_norm > 1e-12:
            q_arr = q_arr / q_norm
        q_vec = q_arr.tolist()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Encoder unavailable for Qdrant path (%s)", exc)
        return None

    qual_results   = qdrant_search.search_qualitative(
        q_vec, limit=5, artist_filter=artist_filter, exclude_ids=excluded_ids,
    )
    lyrics_results = qdrant_search.search_lyrics_chunks(
        q_vec, limit=3, artist_filter=artist_filter, exclude_ids=excluded_ids,
    )

    if qual_results is None or lyrics_results is None:
        # Qdrant became unavailable mid-request; fall back to matrix
        return None

    # Enrich with genre / url / lyrics_snippet from the visible index
    try:
        index      = get_visible_index()
        id_to_song = {s["id"]: s for s in index["songs"]}
    except Exception:
        index      = None
        id_to_song = {}

    def _enrich(r: dict) -> dict:
        meta = id_to_song.get(r["id"], {})
        return {
            **r,
            "genre": meta.get("genre", ""),
            "url":   meta.get("url", ""),
            "lyrics_snippet": r.get("lyrics_snippet") or meta.get("lyrics_snippet", ""),
        }

    suggestions  = [_enrich(r) for r in qual_results]
    lyrics_extra = [_enrich(r) for r in lyrics_results]

    # group_extra via artist embedding column (one matmul, no second encode)
    group_extra = None
    if index is not None:
        ge = compute_group_extra(q_arr, index, exclude_artist_names=excluded_names)
        if ge:
            group_extra = _build_group_extra(*ge[0])

    return {"suggestions": suggestions, "lyrics_extra": lyrics_extra, "group_extra": group_extra}


def _matrix_suggestions(
    q: str,
    excluded_ids: set[int],
    excluded_names: set[str],
) -> dict:
    """Existing matrix-based fallback (top-5000 visible songs)."""
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
        group_extra = _build_group_extra(*scored["group_extra"][0])

    return {
        "suggestions":  [_suggestion_result(songs[i], sc) for i, sc in scored["suggestions"]],
        "lyrics_extra": [_suggestion_result(songs[i], sc) for i, sc in scored["lyrics_extra"]],
        "group_extra":  group_extra,
    }


def _build_group_extra(artist_name: str, score: float) -> dict:
    """Build a group_extra dict from an artist name and cosine score."""
    grup_record = get_index().find_grup_by_name(artist_name)
    clamped = round(max(0.0, min(1.0, float(score))), 4)
    if grup_record is not None:
        return {**_grup_result(grup_record), "score": clamped}
    return {
        "id": 0, "name": artist_name, "song_count": 0,
        "viasona_link": "", "foto": "", "municipi": "", "regio": "", "genres": [],
        "score": clamped,
    }
