"""
Data loading module.

Loads real song data from:
  - embedded_songs.parquet  (embeddings + ids)
  - augmented_songs.csv     (title, artist, album, lyrics)
  - cancons.csv             (url, year, duration)

Falls back to mock_songs.json if the parquet is missing or invalid.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_DATA_DIR   = Path(__file__).parent.parent / "data"
_PARQUET    = _DATA_DIR / "embedded_songs.parquet"
_AUGMENTED  = _DATA_DIR / "augmented_songs.csv"
_CANCONS    = _DATA_DIR / "cancons.csv"
_MOCK       = _DATA_DIR / "mock_songs.json"

_songs_cache: list[dict] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fix_bom_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading BOM / garbage bytes from column names."""
    df.columns = [re.sub(r"^[^\w]+", "", c) for c in df.columns]
    return df


def _embedding_to_list(val) -> list[float]:
    if val is None:
        return []
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            return np.fromstring(val.strip("[]"), sep=",").tolist()
        return []
    try:
        return [float(x) for x in val]
    except (TypeError, ValueError):
        return []


def _extract_year(val) -> int:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0
    try:
        return int(str(val)[:4])
    except (ValueError, TypeError):
        return 0


def _format_duration(val) -> str:
    """Convert pandas timedelta string '0 days 00:04:18' to '4:18'."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    s = str(val).strip()
    if not s or s in ("nan", "NaT", "0 days 00:00:00", "0 days 00:00:00.000000"):
        return ""
    if "days" in s:
        parts = s.split()
        if len(parts) >= 3:
            hms = parts[2].split(":")
            try:
                h, m, sec = int(hms[0]), int(hms[1]), int(float(hms[2])) if len(hms) > 2 else 0
                if h > 0:
                    return f"{h}:{m:02d}:{sec:02d}"
                return f"{m}:{sec:02d}"
            except (ValueError, IndexError):
                pass
    return s


# ---------------------------------------------------------------------------
# Real-data loader
# ---------------------------------------------------------------------------

def _load_from_real_data() -> list[dict]:
    logger.info("Loading embeddings from %s", _PARQUET)

    # 1. Read parquet — only the columns we need
    table = pq.read_table(_PARQUET, columns=["id_lyrics", "embedded_lyrics"])
    emb_df = table.to_pandas()
    logger.info("Parquet: %d rows", len(emb_df))

    parquet_ids: set = set(emb_df["id_lyrics"].tolist())

    # 2. Load augmented_songs.csv in chunks, keep only matching IDs
    aug_chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        _AUGMENTED,
        encoding="latin-1",
        chunksize=100_000,
        dtype={"id_lyrics": "Int64"},
    ):
        chunk = _fix_bom_columns(chunk)
        mask = chunk["id_lyrics"].isin(parquet_ids)
        if mask.any():
            aug_chunks.append(chunk[mask].copy())

    if not aug_chunks:
        raise ValueError("No matching rows in augmented_songs.csv for the embedded IDs")

    aug_df = pd.concat(aug_chunks, ignore_index=True)
    logger.info("augmented_songs matched: %d", len(aug_df))

    # 3. Load cancons.csv in chunks, keep only matching IDs
    cancons_chunks: list[pd.DataFrame] = []
    try:
        for chunk in pd.read_csv(
            _CANCONS,
            chunksize=100_000,
            usecols=["id_lletra", "data", "viasona_link", "durada"],
            dtype={"id_lletra": "Int64"},
        ):
            mask = chunk["id_lletra"].isin(parquet_ids)
            if mask.any():
                cancons_chunks.append(chunk[mask].copy())

        if cancons_chunks:
            cancons_df = pd.concat(cancons_chunks, ignore_index=True)
            cancons_df = cancons_df.rename(columns={"id_lletra": "id_lyrics"})
            # De-duplicate: keep first occurrence per id
            cancons_df = cancons_df.drop_duplicates(subset=["id_lyrics"], keep="first")
        else:
            cancons_df = pd.DataFrame(columns=["id_lyrics", "data", "viasona_link", "durada"])
    except Exception as exc:
        logger.warning("Could not load cancons.csv (%s), skipping", exc)
        cancons_df = pd.DataFrame(columns=["id_lyrics", "data", "viasona_link", "durada"])

    logger.info("cancons matched: %d", len(cancons_df))

    # 4. Merge all three tables
    merged = emb_df.merge(aug_df, on="id_lyrics", how="inner")
    merged = merged.merge(cancons_df, on="id_lyrics", how="left")
    logger.info("Final merged: %d songs", len(merged))

    if merged.empty:
        raise ValueError("Merged DataFrame is empty — check column alignment")

    # 5. Build song dicts
    songs: list[dict] = []
    for _, row in merged.iterrows():
        lyrics = str(row.get("lyrics", "") or "")
        snippet = lyrics[:300].strip()

        songs.append({
            "id":             int(row["id_lyrics"]),
            "title":          str(row.get("title",        "") or ""),
            "artist":         str(row.get("artist",       "") or ""),
            "album":          str(row.get("album",        "") or ""),
            "genre":          "",
            "year":           _extract_year(row.get("data")),
            "lyrics_snippet": snippet,
            "full_lyrics":    lyrics,
            "url":            str(row.get("viasona_link", "") or ""),
            "duration":       _format_duration(row.get("durada")),
            "language":       "Català",
            "embedding":      _embedding_to_list(row["embedded_lyrics"]),
        })

    return songs


def _load_from_mock() -> list[dict]:
    import json
    logger.warning("Falling back to mock_songs.json")
    with open(_MOCK, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_all_songs() -> list[dict]:
    """Load all songs (cached after first call)."""
    global _songs_cache
    if _songs_cache is None:
        try:
            _songs_cache = _load_from_real_data()
        except Exception as exc:
            logger.error("Real-data load failed (%s) — using mock data.", exc)
            _songs_cache = _load_from_mock()
    return _songs_cache


def get_song_by_id(song_id: int) -> dict | None:
    for song in load_all_songs():
        if song["id"] == song_id:
            return song
    return None


def get_songs_by_ids(song_ids: list[int]) -> list[dict]:
    id_set = set(song_ids)
    id_to_song = {s["id"]: s for s in load_all_songs() if s["id"] in id_set}
    return [id_to_song[sid] for sid in song_ids if sid in id_to_song]
