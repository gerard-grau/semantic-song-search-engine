"""
Data loading — fast snapshot first, CSV fallback otherwise.

Three primitives:

* ``load_visible_songs()`` — metadata for the ids in
  ``embedded_songs_2d.parquet``.  No embeddings.
* ``load_all_songs()`` — metadata for every id in ``embedded_songs.parquet``.
  No embeddings.
* ``attach_embeddings(songs)`` — fills the ``embedding`` field in-place,
  reading only the matching rows from ``embedded_songs.parquet`` (PyArrow
  row-group streaming, per-id cache).

If ``songs_meta.parquet`` exists (built by ``data_pipeline``), both loaders
read it directly — instant. Otherwise we fall back to streaming the CSVs,
which is robust but slow (preserved for first-time setups).
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

_DATA_DIR     = Path(__file__).parent.parent / "data"
_PARQUET      = _DATA_DIR / "embedded_songs.parquet"
_PARQUET_2D   = _DATA_DIR / "embedded_songs_2d.parquet"
_META_PARQUET = _DATA_DIR / "songs_meta.parquet"
_AUGMENTED    = _DATA_DIR / "augmented_songs.csv"
_CANCONS      = _DATA_DIR / "cancons.csv"

# Caches
_all_metadata_cache:     list[dict] | None = None
_all_id_index:           dict[int, dict] | None = None
_visible_metadata_cache: list[dict] | None = None
_visible_id_index:       dict[int, dict] | None = None

# ``_embedding_cache[id_lyrics]`` is the ``(F, D)`` float32 matrix of the song's
# F per-field e5 embeddings, in EMBEDDING_FIELD_COLUMNS order. F=5, D=1024.
_embedding_cache:        dict[int, np.ndarray] = {}

# Field order used by the late-fusion scorer.  Add/remove columns here to
# change the multi-field set; the math (max over fields) doesn't care about
# the order, only that all songs share it.
EMBEDDING_FIELD_COLUMNS: tuple[str, ...] = (
    "embedded_lyrics",
    "embedded_qualitative_description",
    "embedded_title",
    "embedded_album",
    "embedded_artist",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _embedding_to_array(val, dim: int | None = None) -> np.ndarray:
    """Parse one parquet embedding cell into a 1-D float32 vector.

    Returns a zero vector of length ``dim`` if parsing fails / value missing.
    """
    if val is None:
        return np.zeros(dim or 0, dtype=np.float32)
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            arr = np.fromstring(s.strip("[]"), sep=",", dtype=np.float32)
            if dim is not None and arr.shape[0] != dim:
                return np.zeros(dim, dtype=np.float32)
            return arr
        return np.zeros(dim or 0, dtype=np.float32)
    try:
        arr = np.asarray(val, dtype=np.float32)
        if dim is not None and arr.shape[0] != dim:
            return np.zeros(dim, dtype=np.float32)
        return arr
    except (TypeError, ValueError):
        return np.zeros(dim or 0, dtype=np.float32)


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
                return f"{h}:{m:02d}:{sec:02d}" if h > 0 else f"{m}:{sec:02d}"
            except (ValueError, IndexError):
                pass
    return s


def _parquet_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    table = pq.read_table(path, columns=["id_lyrics"])
    return {int(x) for x in table.column("id_lyrics").to_pylist()}


def _parquet_ids_ordered(path: Path) -> list[int]:
    """Like ``_parquet_ids`` but preserves the parquet's row order."""
    if not path.exists():
        return []
    table = pq.read_table(path, columns=["id_lyrics"])
    return [int(x) for x in table.column("id_lyrics").to_pylist()]


# ---------------------------------------------------------------------------
# Visible-set selection
# ---------------------------------------------------------------------------

# Hard cap on the number of songs the frontend visualizes at once.
# All songs are still embedded + projected to 2D in the parquets — this only
# limits what we hand to the UI to keep the scatter plot legible.
VISIBLE_SONG_LIMIT = 5000


def select_top_songs(songs: list[dict], limit: int = VISIBLE_SONG_LIMIT) -> list[dict]:
    """
    Pick the songs that get displayed in the visualization.

    Placeholder implementation: returns the first ``limit`` songs in the
    order they were passed in (i.e. parquet row order). Will eventually
    rank by popularity / freshness / curation signals — keep the signature
    stable so callers don't change.
    """
    if limit is None or limit <= 0 or len(songs) <= limit:
        return list(songs)
    return list(songs[:limit])


# ---------------------------------------------------------------------------
# CSV streamer (fallback when songs_meta.parquet is missing)
# ---------------------------------------------------------------------------

def _iter_csv_rows(
    path: Path,
    encoding: str,
    id_column: str,
    wanted_ids: set[int],
    columns: Iterable[str] | None = None,
) -> Iterator[dict]:
    if not path.exists():
        return
    cols_filter = set(columns) if columns is not None else None
    bad_lines = bad_ids = 0
    with open(path, "r", encoding=encoding, newline="", errors="replace") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return
        header = [re.sub(r"^[^\w]+", "", c) for c in header]
        if id_column not in header:
            logger.warning("Column %r missing from %s header.", id_column, path.name)
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
        logger.info("%s: skipped %d malformed rows / %d bad ids", path.name, bad_lines, bad_ids)


def _load_metadata_for_ids(ids: set[int]) -> list[dict]:
    """Fallback CSV streamer used when ``songs_meta.parquet`` is missing."""
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

    cancons_rows = list(_iter_csv_rows(
        _CANCONS, encoding="utf-8", id_column="id_lletra", wanted_ids=ids,
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
        songs.append({
            "id":             int(row["id_lyrics"]),
            "title":          str(row.get("title",        "") or ""),
            "artist":         str(row.get("artist",       "") or ""),
            "album":          str(row.get("album",        "") or ""),
            "genre":          "",
            "year":           _extract_year(row.get("data")),
            "lyrics_snippet": lyrics[:300].strip(),
            "full_lyrics":    lyrics,
            "url":            str(row.get("viasona_link", "") or ""),
            "duration":       _format_duration(row.get("durada")),
            "language":       "Català",
            "embedding":      [],
        })
    return songs


# ---------------------------------------------------------------------------
# Metadata snapshot loader (preferred path)
# ---------------------------------------------------------------------------

def _read_meta_snapshot() -> list[dict] | None:
    """Read ``songs_meta.parquet`` if present. Returns ``None`` on miss."""
    if not _META_PARQUET.exists():
        return None
    try:
        df = pq.read_table(_META_PARQUET).to_pandas()
    except Exception as exc:
        logger.warning("Could not read %s (%s) — falling back to CSVs.", _META_PARQUET, exc)
        return None
    songs: list[dict] = []
    for rec in df.to_dict(orient="records"):
        rec.setdefault("embedding", [])
        rec["id"] = int(rec["id"])
        songs.append(rec)
    return songs


# ---------------------------------------------------------------------------
# Embedding loader (lazy, filtered, streaming)
# ---------------------------------------------------------------------------

def load_embeddings_for_ids(ids: Iterable[int]) -> dict[int, np.ndarray]:
    """Read all ``EMBEDDING_FIELD_COLUMNS`` for the requested ids from parquet.

    Each value in the returned dict is an ``(F, D)`` float32 matrix where
    rows are aligned with ``EMBEDDING_FIELD_COLUMNS``.  Missing or
    malformed cells become zero rows so they contribute nothing under cosine.

    Results are cached per id for the process lifetime.
    """
    wanted = {int(i) for i in ids}
    if not wanted:
        return {}
    missing = wanted - _embedding_cache.keys()
    if missing:
        if not _PARQUET.exists():
            raise FileNotFoundError(f"Embeddings parquet not found at {_PARQUET}.")
        pf = pq.ParquetFile(_PARQUET)
        cols = ["id_lyrics", *EMBEDDING_FIELD_COLUMNS]
        # First pass: peek at row 0 to discover D so zero-fills are sized right.
        dim: int | None = None
        for batch in pf.iter_batches(columns=cols, batch_size=10_000):
            ids_arr = batch.column("id_lyrics").to_pylist()
            field_arrays = [batch.column(c).to_pylist() for c in EMBEDDING_FIELD_COLUMNS]
            if dim is None:
                # Sample any non-empty cell to lock in D.
                for col in field_arrays:
                    for cell in col:
                        arr = _embedding_to_array(cell)
                        if arr.size > 0:
                            dim = int(arr.size)
                            break
                    if dim is not None:
                        break
            for i, sid in enumerate(ids_arr):
                sid = int(sid)
                if sid not in missing or sid in _embedding_cache:
                    continue
                rows = [
                    _embedding_to_array(field_arrays[f][i], dim=dim)
                    for f in range(len(EMBEDDING_FIELD_COLUMNS))
                ]
                _embedding_cache[sid] = np.stack(rows, axis=0).astype(np.float32)
            if not (missing - _embedding_cache.keys()):
                break
    return {sid: _embedding_cache.get(sid) for sid in wanted}


def attach_embeddings(songs: list[dict]) -> list[dict]:
    """Attach per-field embeddings to each song in-place. Idempotent.

    Sets two fields:

    * ``embedding_fields`` — ``(F, D)`` float32 ndarray, F rows aligned with
      ``EMBEDDING_FIELD_COLUMNS``.  Consumed by ``filter_embeddings`` for
      multi-field late-fusion query scoring.
    * ``embedding``        — the lyrics row of ``embedding_fields`` as a
      Python list, preserved for callers that still expect the single-vector
      shape (song-song similarity, neighborhood MDS).
    """
    if not songs:
        return songs
    needed = [s["id"] for s in songs if s.get("embedding_fields") is None]
    if needed:
        emb_map = load_embeddings_for_ids(needed)
        for s in songs:
            if s.get("embedding_fields") is not None:
                continue
            matrix = emb_map.get(s["id"])
            if matrix is None or matrix.size == 0:
                s["embedding_fields"] = None
                s["embedding"] = []
            else:
                s["embedding_fields"] = matrix
                # Lyrics is the first field — keep ``embedding`` as a list so
                # downstream song-song code doesn't need to know about the
                # multi-field structure.
                s["embedding"] = matrix[0].tolist()
    return songs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _ensure_all_metadata() -> None:
    """Populate ``_all_metadata_cache`` once, snapshot-first."""
    global _all_metadata_cache, _all_id_index
    if _all_metadata_cache is not None:
        return
    snap = _read_meta_snapshot()
    if snap is not None:
        logger.info("Loaded %d songs from metadata snapshot.", len(snap))
        _all_metadata_cache = snap
    else:
        ids = _parquet_ids(_PARQUET)
        if not ids:
            raise FileNotFoundError(
                f"Embeddings parquet not found at {_PARQUET}. "
                "Generate it with the embedding pipeline before starting the API."
            )
        logger.info("Streaming metadata for %d catalog songs (CSV fallback) …", len(ids))
        _all_metadata_cache = _load_metadata_for_ids(ids)
    _all_id_index = {s["id"]: s for s in _all_metadata_cache}


def load_all_songs() -> list[dict]:
    """Metadata for every song with an embedding. No embeddings attached."""
    _ensure_all_metadata()
    return _all_metadata_cache  # type: ignore[return-value]


def load_visible_songs() -> list[dict]:
    """
    Metadata for the songs displayed in the visualization. Cached.

    Reads ``embedded_songs_2d.parquet`` in row order, resolves metadata,
    and then runs ``select_top_songs`` to cap the result at the visible
    limit (default 5000).
    """
    global _visible_metadata_cache, _visible_id_index
    if _visible_metadata_cache is not None:
        return _visible_metadata_cache

    ordered_ids = _parquet_ids_ordered(_PARQUET_2D)
    if not ordered_ids:
        logger.warning("No 2D parquet at %s — load_visible_songs() returns [].", _PARQUET_2D)
        _visible_metadata_cache = []
        _visible_id_index = {}
        return _visible_metadata_cache

    _ensure_all_metadata()
    assert _all_id_index is not None  # populated by _ensure_all_metadata
    full_visible = [_all_id_index[i] for i in ordered_ids if i in _all_id_index]
    _visible_metadata_cache = select_top_songs(full_visible)
    _visible_id_index = {s["id"]: s for s in _visible_metadata_cache}
    logger.info(
        "Resolved %d visible songs (of %d projected, cap=%d).",
        len(_visible_metadata_cache), len(full_visible), VISIBLE_SONG_LIMIT,
    )
    return _visible_metadata_cache


def get_song_by_id(song_id: int) -> dict | None:
    if _visible_id_index and song_id in _visible_id_index:
        return _visible_id_index[song_id]
    if _all_id_index is None:
        _ensure_all_metadata()
    return _all_id_index.get(song_id) if _all_id_index else None


def get_songs_by_ids(song_ids: list[int]) -> list[dict]:
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
            _ensure_all_metadata()
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
