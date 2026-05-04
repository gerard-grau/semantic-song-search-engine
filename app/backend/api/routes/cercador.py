"""API route for the Viasona-style instant search (cercador)."""

from __future__ import annotations

import logging
import math
import unicodedata
from pathlib import Path

import pandas as pd
from fastapi import APIRouter

from app.backend.core.data_loader import load_all_songs

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_NOTICIES = _DATA_DIR / "noticies.csv"
_GRUPS    = _DATA_DIR / "grups.csv"


def _safe_str(val) -> str:
    """Return empty string for None/NaN/empty, otherwise strip the value."""
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    return "" if s in ("nan", "NaN", "None") else s

# ---------------------------------------------------------------------------
# Lazy-loaded singletons
# ---------------------------------------------------------------------------

_parser = None
_noticies_cache: list[dict] | None = None
_grups_cache:    list[dict] | None = None


def _get_noticies() -> list[dict]:
    global _noticies_cache
    if _noticies_cache is None:
        try:
            df = pd.read_csv(
                _NOTICIES,
                usecols=["id_article", "titol", "subtitol", "entrada", "data", "viasona_link"],
                nrows=10_000,   # most recent 10 K articles (CSV is ordered by date DESC)
                dtype={"id_article": "Int64"},
            )
            _noticies_cache = []
            for _, row in df.iterrows():
                snippet = _safe_str(row.get("entrada")) or _safe_str(row.get("subtitol"))
                _noticies_cache.append({
                    "id":           int(row["id_article"]) if pd.notna(row["id_article"]) else 0,
                    "title":        _safe_str(row.get("titol")),
                    "date":         _safe_str(row.get("data"))[:10],
                    "snippet":      snippet[:250],
                    "viasona_link": _safe_str(row.get("viasona_link")),
                })
        except Exception as exc:
            logger.warning("Could not load noticies.csv (%s), returning empty list", exc)
            _noticies_cache = []
    return _noticies_cache


def _get_grups() -> list[dict]:
    global _grups_cache
    if _grups_cache is None:
        try:
            df = pd.read_csv(
                _GRUPS,
                usecols=["id_grup", "nom", "num_cancons", "viasona_link", "foto", "municipi", "regio"],
                dtype={"id_grup": "Int64", "num_cancons": "Int64"},
            )
            _grups_cache = []
            for _, row in df.iterrows():
                _grups_cache.append({
                    "id":           int(row["id_grup"]) if pd.notna(row["id_grup"]) else 0,
                    "name":         _safe_str(row.get("nom")),
                    "song_count":   int(row["num_cancons"]) if pd.notna(row.get("num_cancons")) else 0,
                    "viasona_link": _safe_str(row.get("viasona_link")),
                    "foto":         _safe_str(row.get("foto")),
                    "municipi":     _safe_str(row.get("municipi")),
                    "regio":        _safe_str(row.get("regio")),
                    "genres":       [],
                })
            _grups_cache.sort(key=lambda g: g["name"])
        except Exception as exc:
            logger.warning("Could not load grups.csv (%s), returning empty list", exc)
            _grups_cache = []
    return _grups_cache


def _get_parser():
    global _parser
    if _parser is not None:
        return _parser

    import sys
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    so_path = str(project_root / "searchoptimal")
    if so_path not in sys.path:
        sys.path.insert(0, so_path)

    from parser import CatalanSongQueryParser

    parser = CatalanSongQueryParser()
    try:
        parser.load_lexicon(min_zipf=2.4)
    except Exception:
        pass

    songs = load_all_songs()
    grups = _get_grups()
    noticies = _get_noticies()

    catalog_entries = [{"title": s["title"], "artist": s["artist"]} for s in songs]
    for g in grups:
        catalog_entries.append({"title": g["name"], "artist": ""})
    for n in noticies:
        catalog_entries.append({"title": n["title"], "artist": ""})

    parser.load_catalog(catalog_entries)
    _parser = parser
    return parser


# ---------------------------------------------------------------------------
# Fuzzy matching helpers
# ---------------------------------------------------------------------------

def _normalize_for_match(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).replace("·", "")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


@router.get("/cercador")
def cercador_search(q: str = ""):
    """
    Instant search. Returns:
      - grups   (artists from grups.csv)
      - cancons (songs from loaded song catalog)
      - noticies (news articles from noticies.csv)
    """
    q = q.strip()
    if not q:
        return {"grups": [], "cancons": [], "noticies": [], "correction": None}

    songs    = load_all_songs()
    noticies = _get_noticies()
    grups    = _get_grups()

    parser = _get_parser()
    parsed = parser.parse(q, top_k_suggestions=4)

    q_norm        = _normalize_for_match(q)
    corrected_norm = _normalize_for_match(parsed["corrected"]) if parsed["corrected"] else q_norm

    search_terms: set[str] = {q_norm}
    if corrected_norm and corrected_norm != q_norm:
        search_terms.add(corrected_norm)
    for w in corrected_norm.split():
        if len(w) >= 4:
            search_terms.add(w)
    if parsed.get("matched_artist"):
        search_terms.add(_normalize_for_match(parsed["matched_artist"]))
    if parsed.get("matched_title"):
        search_terms.add(_normalize_for_match(parsed["matched_title"]))

    def _matches(text: str) -> bool:
        text_norm = _normalize_for_match(text)
        return any(t in text_norm for t in search_terms)

    # --- Search grups ---
    matched_grups: list[dict] = []
    for grup in grups:
        if _matches(grup["name"]):
            matched_grups.append(grup)
    if parsed.get("matched_artist"):
        ma = parsed["matched_artist"]
        if not any(g["name"] == ma for g in matched_grups):
            entry = next((g for g in grups if g["name"] == ma), None)
            if entry:
                matched_grups.insert(0, entry)
        else:
            matched_grups.sort(key=lambda g: 0 if g["name"] == ma else 1)
    matched_grups = matched_grups[:5]

    # --- Search songs ---
    matched_songs: list[dict] = []
    seen_song_ids: set[int] = set()

    if parsed.get("matched_title"):
        mt = parsed["matched_title"]
        for s in songs:
            if s["title"] == mt and s["id"] not in seen_song_ids:
                matched_songs.append(_song_result(s))
                seen_song_ids.add(s["id"])

    for song in songs:
        if song["id"] in seen_song_ids:
            continue
        if (
            _matches(song["title"])
            or _matches(song["artist"])
            or _matches(song.get("lyrics_snippet", ""))
        ):
            matched_songs.append(_song_result(song))
            seen_song_ids.add(song["id"])
            if len(matched_songs) >= 8:
                break
    matched_songs = matched_songs[:8]

    # --- Search noticies ---
    matched_noticies: list[dict] = []
    for noticia in noticies:
        if _matches(noticia["title"]) or _matches(noticia.get("snippet", "")):
            matched_noticies.append(noticia)
    matched_noticies = matched_noticies[:5]

    # Correction info
    correction = None
    if parsed["corrected"].lower() != q.lower() and parsed["distance"] > 0:
        correction = {
            "corrected":   parsed["corrected"],
            "suggestions": parsed["suggestions"],
        }

    return {
        "grups":      matched_grups,
        "cancons":    matched_songs,
        "noticies":   matched_noticies,
        "correction": correction,
    }


def _song_result(song: dict) -> dict:
    return {
        "id":             song["id"],
        "title":          song["title"],
        "artist":         song["artist"],
        "lyrics_snippet": song.get("lyrics_snippet", ""),
        "genre":          song.get("genre", ""),
        "url":            song.get("url", ""),
    }
