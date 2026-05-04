"""
Data loading module — real data only, with lazy / filtered I/O.

Three primitives:

* ``load_visible_songs()`` — fast. Reads metadata (title, artist, lyrics, …)
  only for the IDs present in ``embedded_songs_2d.parquet``. NO embeddings
  are loaded. This is what /api/songs uses, so the visualization page never
  needs to materialise the multi-GB embedding matrix.

* ``load_all_songs()`` — full catalogue metadata, no embeddings. Used by
  cercador / song-detail pages where any song may be looked up.

* ``attach_embeddings(songs)`` — lazily fills the ``embedding`` field on a
  small set of songs (typically the visible subset, or the survivors of a
  filter), reading only the matching rows from ``embedded_songs.parquet``
  with PyArrow row-group streaming. Embeddings are cached per-ID for the
  process lifetime so repeat calls are free.
"""

from __future__ import annotations

import csv
import logging
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# Some lyrics fields are very long — bump the csv module's per-field cap.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

logger = logging.getLogger(__name__)

_DATA_DIR    = Path(__file__).parent.parent / "data"
_PARQUET     = _DATA_DIR / "embedded_songs.parquet"
_PARQUET_2D  = _DATA_DIR / "embedded_songs_2d.parquet"
_AUGMENTED   = _DATA_DIR / "augmented_songs.csv"
_CANCONS     = _DATA_DIR / "cancons.csv"

# Caches
_all_metadata_cache: list[dict] | None = None
_all_id_index:       dict[int, dict] | None = None

_visible_metadata_cache: list[dict] | None = None
_visible_id_index:       dict[int, dict] | None = None

_embedding_cache: dict[int, list[float]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fix_bom_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [re.sub(r"^[^\w]+", "", c) for c in df.columns]
    return df


def _embedding_to_list(val) -> list[float]:
    if val is None:
        return []
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            return np.fromstring(s.strip("[]"), sep=",").tolist()
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


def _parquet_ids() -> set[int]:
    """Read just the id_lyrics column from the embeddings parquet."""
    if not _PARQUET.exists():
        raise FileNotFoundError(
            f"Embeddings parquet not found at {_PARQUET}. "
            "Generate it with the embedding pipeline before starting the API."
        )
    table = pq.read_table(_PARQUET, columns=["id_lyrics"])
    return {int(x) for x in table.column("id_lyrics").to_pylist()}


def _visible_ids() -> set[int]:
    """IDs present in embedded_songs_2d.parquet — i.e. the songs to display."""
    if not _PARQUET_2D.exists():
        return set()
    table = pq.read_table(_PARQUET_2D, columns=["id_lyrics"])
    return {int(x) for x in table.column("id_lyrics").to_pylist()}


# ---------------------------------------------------------------------------
# Metadata loaders (no embeddings)
# ---------------------------------------------------------------------------

def _iter_csv_rows(
    path: Path,
    encoding: str,
    id_column: str,
    wanted_ids: set[int],
    columns: Iterable[str] | None = None,
) -> Iterator[dict]:
    """
    Robust CSV streamer that survives malformed rows.

    Iterates the file with the stdlib ``csv`` reader (which is more permissive
    than pandas) and skips any row that:

      * fails to parse (``csv.Error`` from unbalanced quotes / stray commas)
      * has the wrong number of columns
      * has a non-numeric ID
      * has an ID not in ``wanted_ids``

    Yields one dict-per-row for the rows that pass.
    """
    if not path.exists():
        return

    cols_filter = set(columns) if columns is not None else None

    bad_lines = 0
    bad_ids = 0
    with open(path, "r", encoding=encoding, newline="", errors="replace") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return
        # strip BOM / leading non-word chars on the first column name
        header = [re.sub(r"^[^\w]+", "", c) for c in header]
        if id_column not in header:
            logger.warning("Column %r not in %s header (%s)", id_column, path.name, header)
            return
        n_cols = len(header)
        id_index = header.index(id_column)

        while True:
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error:
                bad_lines += 1
                continue
            if len(row) != n_cols:
                bad_lines += 1
                continue
            try:
                sid = int(row[id_index])
            except (ValueError, TypeError):
                bad_ids += 1
                continue
            if sid not in wanted_ids:
                continue
            if cols_filter is None:
                yield dict(zip(header, row))
            else:
                yield {h: v for h, v in zip(header, row) if h in cols_filter}

    if bad_lines or bad_ids:
        logger.info(
            "%s: skipped %d malformed rows and %d non-numeric IDs",
            path.name, bad_lines, bad_ids,
        )


def _load_metadata_for_ids(ids: set[int]) -> list[dict]:
    """Stream augmented_songs.csv + cancons.csv; keep only the requested IDs."""
    if not ids:
        return []
    if not _AUGMENTED.exists():
        raise FileNotFoundError(f"augmented_songs.csv not found at {_AUGMENTED}")

    aug_rows = list(_iter_csv_rows(
        _AUGMENTED, encoding="latin-1", id_column="id_lyrics", wanted_ids=ids,
    ))
    if not aug_rows:
        return []
    aug_df = pd.DataFrame(aug_rows)
    aug_df["id_lyrics"] = aug_df["id_lyrics"].astype("int64")

    # cancons.csv keys by id_lletra (≡ id_lyrics)
    cancons_rows = list(_iter_csv_rows(
        _CANCONS,
        encoding="utf-8",
        id_column="id_lletra",
        wanted_ids=ids,
        columns=("id_lletra", "data", "viasona_link", "durada"),
    ))
    if cancons_rows:
        cancons_df = pd.DataFrame(cancons_rows)
        cancons_df["id_lletra"] = cancons_df["id_lletra"].astype("int64")
        cancons_df = (
            cancons_df.rename(columns={"id_lletra": "id_lyrics"})
                      .drop_duplicates(subset=["id_lyrics"], keep="first")
        )
    else:
        cancons_df = pd.DataFrame(columns=["id_lyrics", "data", "viasona_link", "durada"])

    merged = aug_df.merge(cancons_df, on="id_lyrics", how="left")

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
            "embedding":      [],   # filled lazily by attach_embeddings()
        })

    return songs


# ---------------------------------------------------------------------------
# Embedding loader (lazy, filtered, streaming)
# ---------------------------------------------------------------------------

def load_embeddings_for_ids(ids: Iterable[int]) -> dict[int, list[float]]:
    """
    Read ``embedded_songs.parquet`` row-group by row-group and keep only the
    rows whose id_lyrics is in ``ids``. Each id is cached after first load.
    """
    wanted = {int(i) for i in ids}
    if not wanted:
        return {}

    missing = wanted - _embedding_cache.keys()
    if missing:
        if not _PARQUET.exists():
            raise FileNotFoundError(
                f"Embeddings parquet not found at {_PARQUET}."
            )
        pf = pq.ParquetFile(_PARQUET)
        for batch in pf.iter_batches(
            columns=["id_lyrics", "embedded_lyrics"],
            batch_size=10_000,
        ):
            ids_arr   = batch.column("id_lyrics").to_pylist()
            embs_arr  = batch.column("embedded_lyrics").to_pylist()
            for sid, emb in zip(ids_arr, embs_arr):
                sid = int(sid)
                if sid in missing and sid not in _embedding_cache:
                    _embedding_cache[sid] = _embedding_to_list(emb)
            if not (missing - _embedding_cache.keys()):
                break

    return {sid: _embedding_cache.get(sid, []) for sid in wanted}


def attach_embeddings(songs: list[dict]) -> list[dict]:
    """Fill the ``embedding`` field of each song in-place. Idempotent."""
    if not songs:
        return songs
    needed = [s["id"] for s in songs if not s.get("embedding")]
    if needed:
        emb_map = load_embeddings_for_ids(needed)
        for s in songs:
            if not s.get("embedding"):
                s["embedding"] = emb_map.get(s["id"], [])
    return songs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_visible_songs() -> list[dict]:
    """
    Metadata for the songs that have a 2D projection. Cached.
    Cheap: reads only one column from ``embedded_songs_2d.parquet`` plus the
    metadata rows for those IDs. Embeddings are NOT loaded.
    """
    global _visible_metadata_cache, _visible_id_index
    if _visible_metadata_cache is None:
        ids = _visible_ids()
        if not ids:
            logger.warning(
                "No 2D parquet found at %s — load_visible_songs() returning [].",
                _PARQUET_2D,
            )
            _visible_metadata_cache = []
            _visible_id_index = {}
        else:
            logger.info("Loading metadata for %d visible songs …", len(ids))
            _visible_metadata_cache = _load_metadata_for_ids(ids)
            _visible_id_index = {s["id"]: s for s in _visible_metadata_cache}
    return _visible_metadata_cache


def load_all_songs() -> list[dict]:
    """
    Metadata for every song that has an embedding (full catalog). Cached.
    Used by cercador and song-detail. NO embeddings — call
    ``attach_embeddings()`` if you need them.
    """
    global _all_metadata_cache, _all_id_index
    if _all_metadata_cache is None:
        ids = _parquet_ids()
        logger.info("Loading metadata for %d catalog songs …", len(ids))
        _all_metadata_cache = _load_metadata_for_ids(ids)
        _all_id_index = {s["id"]: s for s in _all_metadata_cache}
    return _all_metadata_cache


def get_song_by_id(song_id: int) -> dict | None:
    """Look up a song by ID. Tries the visible cache first (cheap), then the
    full catalog cache (loads on first miss)."""
    if _visible_id_index and song_id in _visible_id_index:
        return _visible_id_index[song_id]
    if _all_id_index is None:
        load_all_songs()
    return _all_id_index.get(song_id) if _all_id_index else None


def get_songs_by_ids(song_ids: list[int]) -> list[dict]:
    """Same multi-tier lookup as get_song_by_id, batched."""
    out: list[dict] = []
    missing: list[int] = []
    if _visible_id_index:
        for sid in song_ids:
            song = _visible_id_index.get(sid)
            if song is not None:
                out.append(song)
            else:
                missing.append(sid)
    else:
        missing = list(song_ids)

    if missing:
        if _all_id_index is None:
            load_all_songs()
        if _all_id_index:
            for sid in missing:
                song = _all_id_index.get(sid)
                if song is not None:
                    out.append(song)
    return out


def invalidate_cache() -> None:
    """Drop all in-memory caches — call after regenerating data files."""
    global _all_metadata_cache, _all_id_index
    global _visible_metadata_cache, _visible_id_index
    _all_metadata_cache = None
    _all_id_index = None
    _visible_metadata_cache = None
    _visible_id_index = None
    _embedding_cache.clear()
