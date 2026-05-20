"""
Helpers for the in-progress genre relabelling job.

Provides:
  - GENRES tuple (11 labels, matches _genres.py)
  - load_top_5000(): returns list of dicts {rank, title, artist, ...}
  - load_lyrics_index(): returns dict mapping normalize(artist)+'|'+normalize(title)
                          -> {lyrics, description}
  - normalize(): accent-stripping + lowercasing for cross-CSV matching
                 (augmented_songs.csv has mojibake so we strip aggressively)
  - lookup(artist, title): convenience to fetch lyrics+description for a song
  - read_labels_csv(): load current state of genre_labels.csv (resume support)
  - append_labels(rows): append-and-flush rows to genre_labels.csv
"""
from __future__ import annotations

import csv
import io
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_5000 = ROOT / "app/backend/data/processed/top_5000_songs.csv"
AUGMENTED = ROOT / "app/backend/data/raw/augmented_songs.csv"
LABELS_CSV = ROOT / "app/backend/data/processed/genre_labels.csv"

GENRES: tuple[str, ...] = (
    "cançó d'autor",
    "folk",
    "tradicional",
    "rock",
    "pop",
    "rumba",
    "música urbana",
    "infantil",
    "mestissa",
)


_NON_MATCH = re.compile(r"[^a-z0-9?]+")


def normalize(s: str) -> str:
    """Match-friendly normalization that works around mojibake in augmented_songs.csv.

    The mojibake replaces accented letters with `�`. The clean top_5000.csv keeps
    them. To make both match, we collapse *any* non-ASCII glyph (mojibake or
    real accent) to a single wildcard `?`, then strip whitespace/punctuation
    and lowercase.

      'Llu�s Llach'  ->  'llu?sllach'
      'Lluís Llach'  ->  'llu?sllach'
    """
    if s is None:
        return ""
    out_chars = []
    for c in s:
        if c == "�":
            out_chars.append("?")
        elif ord(c) < 128:
            out_chars.append(c)
        else:
            # any non-ASCII glyph (accented letter, ñ, ç, etc.) -> wildcard
            out_chars.append("?")
    s = "".join(out_chars).lower()
    s = _NON_MATCH.sub("", s)
    return s


def load_top_5000() -> list[dict]:
    rows = []
    with open(TOP_5000, encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({
                "rank": int(row["#"]),
                "title": row["song_title"],
                "artist": row["artist"],
                "views": int(row["views"]) if row.get("views") else 0,
            })
    return rows


_lyrics_cache: dict[str, dict] | None = None
_artist_cache: dict[str, list[dict]] | None = None


def _load_augmented_raw() -> list[dict]:
    with open(AUGMENTED, "rb") as f:
        raw = f.read()
    if raw and raw[0] == 0xff:
        raw = raw[1:]
    text = raw.decode("utf-8", errors="replace")
    r = csv.DictReader(io.StringIO(text))
    return list(r)


def load_lyrics_index() -> dict[str, dict]:
    """Returns: normalize(artist)+'|'+normalize(title) -> {lyrics, description, artist_raw, title_raw}"""
    global _lyrics_cache
    if _lyrics_cache is not None:
        return _lyrics_cache
    rows = _load_augmented_raw()
    idx: dict[str, dict] = {}
    for row in rows:
        key = normalize(row.get("artist", "")) + "|" + normalize(row.get("title", ""))
        if key in idx:
            continue  # first wins
        idx[key] = {
            "lyrics": row.get("lyrics") or "",
            "description": row.get("qualitative_description") or "",
            "artist_raw": row.get("artist") or "",
            "title_raw": row.get("title") or "",
        }
    _lyrics_cache = idx
    return idx


def load_artist_index() -> dict[str, list[dict]]:
    """Returns: normalize(artist) -> list of {title, lyrics, description} from
    augmented_songs.csv (useful when title doesn't match but you want to see what
    other songs the artist has)."""
    global _artist_cache
    if _artist_cache is not None:
        return _artist_cache
    rows = _load_augmented_raw()
    idx: dict[str, list[dict]] = {}
    for row in rows:
        a = normalize(row.get("artist", ""))
        if not a:
            continue
        idx.setdefault(a, []).append({
            "title": row.get("title") or "",
            "lyrics": row.get("lyrics") or "",
            "description": row.get("qualitative_description") or "",
        })
    _artist_cache = idx
    return idx


def lookup(artist: str, title: str) -> dict | None:
    """Return {lyrics, description, ...} for a song, or None if not found.

    Tries the literal (artist, title) first, then each comma-separated
    collaborator individually, then any artist that contains the song
    with that title."""
    idx = load_lyrics_index()
    key = normalize(artist) + "|" + normalize(title)
    if key in idx:
        return idx[key]
    # Try comma-separated collaborators (e.g. "31 FAM, Flashy Ice Cream")
    for part in artist.split(","):
        part = part.strip()
        if not part:
            continue
        k = normalize(part) + "|" + normalize(title)
        if k in idx:
            return idx[k]
    # Final fallback: search the artist index for an artist that contains
    # one of the names, and whose track list includes this title.
    arts = load_artist_index()
    target_title = normalize(title)
    for part in artist.split(","):
        np = normalize(part.strip())
        if not np:
            continue
        for akey, songs in arts.items():
            if np in akey or akey in np:
                for s in songs:
                    if normalize(s["title"]) == target_title:
                        return {
                            "lyrics": s["lyrics"],
                            "description": s["description"],
                            "artist_raw": akey,
                            "title_raw": s["title"],
                        }
    return None


def short_description(artist: str, title: str, max_chars: int = 200) -> str:
    """Best-effort one-line summary for a song: prefer qualitative_description,
    fall back to first lyrics line."""
    hit = lookup(artist, title)
    if not hit:
        return ""
    desc = hit["description"].strip()
    if desc:
        return desc[:max_chars]
    lyrics = hit["lyrics"].strip()
    if lyrics:
        first = lyrics.split("\n", 1)[0]
        return first[:max_chars]
    return ""


def read_labels_csv() -> dict[int, str]:
    """Load the current state of genre_labels.csv -> {rank: genre}.
    Returns empty dict if the file doesn't exist (start of run)."""
    if not LABELS_CSV.exists():
        return {}
    out: dict[int, str] = {}
    with open(LABELS_CSV, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            out[int(row["rank"])] = row["genre"]
    return out


def append_labels(rows: list[dict]) -> None:
    """Append {rank, title, artist, genre, note} rows to genre_labels.csv.
    Creates the file with header if it doesn't exist yet."""
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LABELS_CSV.exists()
    with open(LABELS_CSV, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rank", "title", "artist", "genre", "note"])
        if is_new:
            w.writeheader()
        for row in rows:
            assert row["genre"] in GENRES, f"bad genre {row['genre']!r} at rank {row['rank']}"
            w.writerow(row)
