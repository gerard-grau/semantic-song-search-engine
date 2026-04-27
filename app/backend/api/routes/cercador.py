"""API route for the Viasona-style instant search (cercador)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from app.backend.core.data_loader import load_all_songs

# ---------------------------------------------------------------------------
# Lazy-loaded parser singleton
# ---------------------------------------------------------------------------

_parser = None
_noticies: list[dict] | None = None
_artists_set: list[dict] | None = None

def _get_noticies() -> list[dict]:
    global _noticies
    if _noticies is None:
        # routes -> api -> backend
        p = Path(__file__).resolve().parent.parent.parent / "data" / "mock_noticies.json"
        with open(p, "r", encoding="utf-8") as f:
            _noticies = json.load(f)
    return _noticies


def _get_artists(songs: list[dict]) -> list[dict]:
    """Build a deduplicated artist list from songs."""
    global _artists_set
    if _artists_set is not None:
        return _artists_set
    seen: dict[str, dict] = {}
    for s in songs:
        name = s.get("artist", "").strip()
        if name and name not in seen:
            song_count = sum(1 for x in songs if x.get("artist") == name)
            genres = list({x["genre"] for x in songs if x.get("artist") == name})
            seen[name] = {
                "name": name,
                "song_count": song_count,
                "genres": genres,
            }
    _artists_set = sorted(seen.values(), key=lambda a: a["name"])
    return _artists_set


def _get_parser():
    global _parser
    if _parser is not None:
        return _parser

    import sys, os
    # Add searchoptimal to path (routes -> api -> backend -> app -> project_root)
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    so_path = str(project_root / "searchoptimal")
    if so_path not in sys.path:
        sys.path.insert(0, so_path)

    from parser import CatalanSongQueryParser

    parser = CatalanSongQueryParser()
    try:
        parser.load_lexicon(min_zipf=2.4)
    except Exception:
        pass  # wordfreq may not be installed

    # Load catalog from songs + noticies artists
    songs = load_all_songs()
    catalog_entries = [{"title": s["title"], "artist": s["artist"]} for s in songs]

    # Also add noticia titles as "titles" so they're searchable
    for n in _get_noticies():
        catalog_entries.append({"title": n["title"], "artist": ""})

    parser.load_catalog(catalog_entries)
    _parser = parser
    return parser


# ---------------------------------------------------------------------------
# Fuzzy matching helpers (accent-insensitive, substring)
# ---------------------------------------------------------------------------

def _normalize_for_match(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).replace('·', '')



# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


@router.get("/cercador")
def cercador_search(q: str = ""):
    """
    Instant search endpoint. Returns categorised results:
    - grups (artists)
    - cançons (songs with lyrics snippets)
    - noticies (news articles)

    Uses the parser for fuzzy/corrected matching, then also does
    simple substring matching to catch partial typing.
    """
    q = q.strip()
    if not q:
        return {"grups": [], "cancons": [], "noticies": [], "correction": None}

    songs = load_all_songs()
    noticies = _get_noticies()
    artists = _get_artists(songs)

    # Run parser for correction and suggestions
    parser = _get_parser()
    parsed = parser.parse(q, top_k_suggestions=4)

    q_norm = _normalize_for_match(q)
    corrected_norm = _normalize_for_match(parsed["corrected"]) if parsed["corrected"] else q_norm

    # Search terms: original query + corrected form only (not the full word bag,
    # which is too noisy). Individual corrected words are added only if they
    # come from the corrected phrase (not from distant suggestions).
    search_terms: set[str] = {q_norm}
    if corrected_norm and corrected_norm != q_norm:
        search_terms.add(corrected_norm)
    # Add individual words from the corrected phrase (not the full bag).
    # Min length 4 to avoid matching common short words like "per", "els".
    for w in corrected_norm.split():
        if len(w) >= 4:
            search_terms.add(w)

    # If parser matched a specific artist/title, add those as terms too
    if parsed.get("matched_artist"):
        search_terms.add(_normalize_for_match(parsed["matched_artist"]))
    if parsed.get("matched_title"):
        search_terms.add(_normalize_for_match(parsed["matched_title"]))

    def _matches(text: str) -> bool:
        text_norm = _normalize_for_match(text)
        return any(t in text_norm for t in search_terms)

    # --- Search artists ---
    matched_grups = []
    for artist in artists:
        if _matches(artist["name"]):
            matched_grups.append(artist)
    # Ensure parser-matched artist is first
    if parsed.get("matched_artist"):
        ma = parsed["matched_artist"]
        if not any(a["name"] == ma for a in matched_grups):
            a_entry = next((a for a in artists if a["name"] == ma), None)
            if a_entry:
                matched_grups.insert(0, a_entry)
        else:
            # Move to front
            matched_grups.sort(key=lambda a: 0 if a["name"] == ma else 1)
    matched_grups = matched_grups[:5]

    # --- Search songs (lletres) ---
    matched_songs = []
    seen_song_ids: set[int] = set()

    # Parser-matched title songs first
    if parsed.get("matched_title"):
        mt = parsed["matched_title"]
        for s in songs:
            if s["title"] == mt and s["id"] not in seen_song_ids:
                matched_songs.append(_song_result(s))
                seen_song_ids.add(s["id"])

    for song in songs:
        if song["id"] in seen_song_ids:
            continue
        if (_matches(song["title"]) or _matches(song["artist"])
                or _matches(song.get("lyrics_snippet", ""))):
            matched_songs.append(_song_result(song))
            seen_song_ids.add(song["id"])
            if len(matched_songs) >= 8:
                break
    matched_songs = matched_songs[:8]

    # --- Search noticies ---
    matched_noticies = []
    for noticia in noticies:
        if _matches(noticia["title"]) or _matches(noticia.get("snippet", "")):
            matched_noticies.append(noticia)
    matched_noticies = matched_noticies[:5]

    # Build correction info
    correction = None
    if parsed["corrected"].lower() != q.lower() and parsed["distance"] > 0:
        correction = {
            "corrected": parsed["corrected"],
            "suggestions": parsed["suggestions"],
        }

    return {
        "grups": matched_grups,
        "cancons": matched_songs,
        "noticies": matched_noticies,
        "correction": correction,
    }


def _song_result(song: dict) -> dict:
    return {
        "id": song["id"],
        "title": song["title"],
        "artist": song["artist"],
        "lyrics_snippet": song.get("lyrics_snippet", ""),
        "genre": song.get("genre", ""),
    }
