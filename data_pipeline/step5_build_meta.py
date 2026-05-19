"""
Step 5 — build ``songs_meta.parquet``: the metadata snapshot consumed by
``app/backend/core/data_loader``.

Reads ``embedded_songs.parquet`` for the canonical id list, joins
``augmented_songs.csv`` (title/artist/album/lyrics) and ``cancons.csv``
(year/duration/viasona_link), then joins the genre column from
``embedded_songs_genres.parquet``.

Output columns:
    id, title, artist, album, genre, year, lyrics_snippet, full_lyrics,
    url, duration, language
"""

from __future__ import annotations

import argparse
import csv as _csv
import logging
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ._paths import (
    AUGMENTED_CSV, CANCONS_CSV, EMBEDDED_PARQUET,
    GENRES_PARQUET, META_PARQUET,
)

_csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────

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
                h = int(hms[0]); m = int(hms[1]); sec = int(float(hms[2])) if len(hms) > 2 else 0
                return f"{h}:{m:02d}:{sec:02d}" if h > 0 else f"{m}:{sec:02d}"
            except (ValueError, IndexError):
                pass
    return s


def _iter_csv_rows(path: Path, encoding: str, id_column: str,
                   wanted_ids: set[int], columns: Iterable[str] | None = None
                   ) -> Iterator[dict]:
    if not path.exists():
        return
    cols_filter = set(columns) if columns is not None else None
    bad_lines = bad_ids = 0
    with open(path, "r", encoding=encoding, newline="", errors="replace") as fh:
        reader = _csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return
        header = [re.sub(r"^[^\w]+", "", c, flags=re.ASCII).lstrip("﻿") for c in header]
        if id_column not in header:
            logger.warning("Column %r missing from %s header.", id_column, path.name)
            return
        n_cols   = len(header)
        id_index = header.index(id_column)
        for row in reader:
            try:
                if len(row) != n_cols:
                    bad_lines += 1
                    continue
            except _csv.Error:
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
        logger.info("%s: skipped %d malformed rows / %d bad ids.",
                    path.name, bad_lines, bad_ids)


def _build(ids: set[int]) -> list[dict]:
    """Build the metadata snapshot dicts for the given ids."""
    if not AUGMENTED_CSV.exists():
        raise FileNotFoundError(f"augmented_songs.csv not found at {AUGMENTED_CSV}")

    aug_rows = list(_iter_csv_rows(
        AUGMENTED_CSV, encoding="latin-1", id_column="id_lyrics", wanted_ids=ids,
    ))
    if not aug_rows:
        raise RuntimeError(
            f"No matching rows in {AUGMENTED_CSV} for {len(ids)} ids — file may be stale."
        )
    aug_df = pd.DataFrame(aug_rows)
    aug_df["id_lyrics"] = aug_df["id_lyrics"].astype("int64")

    cancons_rows = list(_iter_csv_rows(
        CANCONS_CSV, encoding="utf-8", id_column="id_lletra", wanted_ids=ids,
        columns=("id_lletra", "data", "viasona_link", "durada"),
    ))
    if cancons_rows:
        cdf = pd.DataFrame(cancons_rows)
        cdf["id_lletra"] = cdf["id_lletra"].astype("int64")
        cdf = (cdf.rename(columns={"id_lletra": "id_lyrics"})
                  .drop_duplicates(subset=["id_lyrics"], keep="first"))
    else:
        logger.warning("cancons.csv produced no matching rows — year/url/duration left empty.")
        cdf = pd.DataFrame(columns=["id_lyrics", "data", "viasona_link", "durada"])

    merged = aug_df.merge(cdf, on="id_lyrics", how="left")
    songs: list[dict] = []
    for _, row in merged.iterrows():
        lyrics = str(row.get("lyrics", "") or "")
        songs.append({
            "id":             int(row["id_lyrics"]),
            "title":          str(row.get("title",  "") or ""),
            "artist":         str(row.get("artist", "") or ""),
            "album":          str(row.get("album",  "") or ""),
            "genre":          "",
            "year":           _extract_year(row.get("data")),
            "lyrics_snippet": lyrics[:300].strip(),
            "full_lyrics":    lyrics,
            "url":            str(row.get("viasona_link", "") or ""),
            "duration":       _format_duration(row.get("durada")),
            "language":       "Català",
        })
    return songs


def _join_genre(songs: list[dict]) -> None:
    if not GENRES_PARQUET.exists():
        logger.info("No %s — genre column left empty.", GENRES_PARQUET.name)
        return
    gdf = pq.read_table(GENRES_PARQUET, columns=["id_lyrics", "genre"]).to_pandas()
    gdf["id_lyrics"] = gdf["id_lyrics"].astype("int64")
    genre_map = {int(i): str(g) for i, g in zip(gdf["id_lyrics"], gdf["genre"])}
    filled = 0
    for s in songs:
        g = genre_map.get(int(s["id"]))
        if g:
            s["genre"] = g
            filled += 1
    logger.info("Joined genre on %d / %d songs from %s.",
                filled, len(songs), GENRES_PARQUET.name)


def run(force: bool = False) -> dict:
    if META_PARQUET.exists() and not force:
        logger.info("%s already exists — skipping. Use --force to rebuild.", META_PARQUET)
        return {"skipped": True, "output_file": str(META_PARQUET)}
    if not EMBEDDED_PARQUET.exists():
        raise FileNotFoundError(f"{EMBEDDED_PARQUET} missing.")

    table = pq.read_table(EMBEDDED_PARQUET, columns=["id_lyrics"])
    ids   = {int(x) for x in table.column("id_lyrics").to_pylist()}
    logger.info("Building metadata snapshot for %d catalogue ids …", len(ids))

    songs = _build(ids)
    _join_genre(songs)

    df = pd.DataFrame(songs)
    META_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    if META_PARQUET.exists():
        META_PARQUET.unlink()
    df.to_parquet(META_PARQUET, index=False)
    logger.info("Wrote %d rows to %s", len(df), META_PARQUET)
    return {"rows": len(df), "output_file": str(META_PARQUET)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true",
                   help="Rebuild even if songs_meta.parquet exists.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(run(force=args.force))


if __name__ == "__main__":
    main()
