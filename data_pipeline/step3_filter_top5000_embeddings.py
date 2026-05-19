"""
Step 3 — slice ``embedded_songs.parquet`` down to the 5000 visible songs.

Writes ``embedded_songs_top5000.parquet`` with one row per
``(id_lyrics, artist)`` pair from ``top_5000_songs.csv``, in popularity
order, columns ``id_lyrics, artist, <embedding cols…>``.

Why two-pointer alignment:
    Some songs (collabs) share ``id_lyrics`` but are stored as separate rows
    in ``augmented_songs.csv`` — one per artist — with one embedding row each
    in the parquet. Deduping purely by ``id_lyrics`` would pick the wrong
    artist's embedding. We recover the row-level mapping by walking both
    ``augmented_songs.csv`` and the parquet in lockstep on ``id_lyrics``.
"""

from __future__ import annotations

import argparse
import csv as _csv
import logging
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ._paths import AUGMENTED_CSV, EMBEDDED_PARQUET, TOP5000_CSV, TOP5K_PARQUET

_csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
logger = logging.getLogger(__name__)


def _norm_key(s) -> str:
    if s is None:
        return ""
    text = unicodedata.normalize("NFKD", str(s))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower().strip())


def _load_augmented(path: Path) -> pd.DataFrame:
    """Load augmented_songs.csv tolerantly.

    The file ships with a stray leading 0xff byte (UTF-16 BOM relic) which
    makes UTF-8 decoding fail. We read it as ``latin-1`` and normalise the
    header so the first column ends up as ``artist`` (rather than
    ``ÿartist``), matching what the rest of the backend expects.
    """
    if not path.exists():
        raise FileNotFoundError(f"augmented_songs.csv not found at {path}")
    df = pd.read_csv(
        path, encoding="latin-1", engine="python",
        on_bad_lines="skip",
    )
    df.columns = [re.sub(r"^[^\w]+", "", c, flags=re.ASCII).lstrip("﻿") for c in df.columns]
    df = df[["id_lyrics", "artist", "title", "album"]].copy()
    df["id_lyrics"] = pd.to_numeric(df["id_lyrics"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["id_lyrics"]).reset_index(drop=True)
    df["id_lyrics"] = df["id_lyrics"].astype("int64")
    df["row_idx"]   = range(len(df))
    logger.info("Loaded %d augmented rows (%d unique id_lyrics).",
                len(df), df["id_lyrics"].nunique())
    return df


def _align(aug: pd.DataFrame, parquet_path: Path) -> dict[int, int]:
    """Two-pointer walk over ``id_lyrics`` → ``aug_row → parquet_row``.

    Tolerates parquet rows whose ``id_lyrics`` no longer appears in
    ``augmented_songs.csv`` (the CSV has been re-exported and lost some
    songs the embeddings were built from). Such rows are dropped from the
    mapping — we have no metadata to attach to them anyway.
    """
    pq_ids  = pq.read_table(parquet_path, columns=["id_lyrics"]).to_pandas() \
                ["id_lyrics"].astype("int64").to_numpy()
    aug_ids = aug["id_lyrics"].to_numpy()
    aug_set = set(aug_ids.tolist())
    mapping: dict[int, int] = {}
    skipped_pq = 0
    i = j = 0
    while i < len(pq_ids) and j < len(aug_ids):
        if pq_ids[i] == aug_ids[j]:
            mapping[j] = i
            i += 1
            j += 1
        elif pq_ids[i] not in aug_set:
            i += 1
            skipped_pq += 1
        else:
            j += 1
    while i < len(pq_ids) and pq_ids[i] not in aug_set:
        i += 1
        skipped_pq += 1
    if i != len(pq_ids):
        raise RuntimeError(
            f"Alignment exhausted augmented_songs.csv with {len(pq_ids) - i} "
            f"parquet rows unmatched (next pq id={pq_ids[i] if i < len(pq_ids) else 'n/a'}). "
            "embedded_songs.parquet no longer matches augmented_songs.csv row order."
        )
    logger.info("Aligned %d parquet rows (dropped %d augmented rows, skipped %d orphan parquet rows).",
                len(mapping), len(aug_ids) - len(mapping), skipped_pq)
    return mapping


_PAGE_ALBUM_RE = re.compile(r"de l['’]àlbum\s*\"([^\"]+)\"", re.IGNORECASE)


def _album_from_page(page_title: str | None) -> str:
    if not page_title:
        return ""
    m = _PAGE_ALBUM_RE.search(str(page_title))
    return m.group(1).strip() if m else ""


def _build_lookups(aug: pd.DataFrame, aug_to_pq: dict[int, int]):
    by_tri:  dict[tuple, tuple] = {}
    by_pair: dict[tuple, list]  = {}
    for row in aug.itertuples(index=False):
        pq_idx = aug_to_pq.get(row.row_idx)
        if pq_idx is None:
            continue
        t = _norm_key(row.title)
        a = _norm_key(row.artist)
        alb = _norm_key(row.album)
        triple = (pq_idx, int(row.id_lyrics), str(row.artist))
        by_tri.setdefault((t, a, alb), triple)
        by_pair.setdefault((t, a), []).append((pq_idx, int(row.id_lyrics), str(row.artist), alb))
    return by_tri, by_pair


def _pick(candidates, csv_album: str):
    if not candidates:
        return None
    if csv_album:
        for pq_idx, sid, artist, alb_key in candidates:
            if alb_key == csv_album:
                return (pq_idx, sid, artist)
        for pq_idx, sid, artist, alb_key in candidates:
            if csv_album in alb_key:
                return (pq_idx, sid, artist)
    pq_idx, sid, artist, _ = candidates[0]
    return (pq_idx, sid, artist)


def _resolve(top_csv: Path, by_tri, by_pair):
    top = pd.read_csv(top_csv, encoding="utf-8-sig", skipinitialspace=True)
    top.columns = [c.strip().lstrip("#").strip() for c in top.columns]
    if "song_title" not in top.columns or "artist" not in top.columns:
        raise ValueError(
            f"{top_csv} needs 'song_title' and 'artist' columns. Found: {list(top.columns)}"
        )
    has_page = "page_title" in top.columns

    resolved: list[tuple[int, int, str]] = []
    seen: set[int] = set()
    missing = 0
    for i in range(len(top)):
        title  = top["song_title"].iat[i]
        artist = top["artist"].iat[i]
        page   = top["page_title"].iat[i] if has_page else ""
        album  = _album_from_page(page)

        t, a, alb = _norm_key(title), _norm_key(artist), _norm_key(album)
        hit = by_tri.get((t, a, alb)) if alb else None
        if hit is None:
            hit = _pick(by_pair.get((t, a), []), alb)
        if hit is None and "," in str(artist or ""):
            first = _norm_key(str(artist).split(",", 1)[0])
            hit = by_tri.get((t, first, alb)) if alb else None
            if hit is None:
                hit = _pick(by_pair.get((t, first), []), alb)
        if hit is None:
            missing += 1
            continue
        pq_idx, _sid, _ar = hit
        if pq_idx in seen:
            continue
        seen.add(pq_idx)
        resolved.append(hit)
    logger.info("Resolved %d / %d top entries (%d unmatched).",
                len(resolved), len(top), missing)
    return resolved


def _slice(resolved, embed_parquet: Path, output: Path) -> dict:
    if not resolved:
        raise ValueError("No resolved rows — refusing to write empty parquet.")
    wanted    = {row_idx for row_idx, _s, _a in resolved}
    artist_by = {row_idx: artist for row_idx, _s, artist in resolved}
    rank_by   = {row_idx: rank for rank, (row_idx, _s, _a) in enumerate(resolved)}

    pf = pq.ParquetFile(embed_parquet)
    chunks: list[pd.DataFrame] = []
    cursor = 0
    seen   = 0
    for batch in pf.iter_batches(batch_size=10_000):
        end = cursor + batch.num_rows
        in_win = [i for i in range(cursor, end) if i in wanted]
        if in_win:
            df = batch.to_pandas()
            sub = df.iloc[[i - cursor for i in in_win]].copy()
            sub["_pq_row"] = in_win
            chunks.append(sub)
            seen += len(in_win)
        cursor = end
        if seen == len(wanted):
            break

    if seen != len(wanted):
        raise RuntimeError(
            f"Only matched {seen}/{len(wanted)} rows in {embed_parquet} — parquet drift."
        )

    out = pd.concat(chunks, ignore_index=True)
    out["artist"] = out["_pq_row"].map(artist_by)
    out["_rank"]  = out["_pq_row"].map(rank_by)
    out = (out.sort_values("_rank")
              .drop(columns=["_pq_row", "_rank"])
              .reset_index(drop=True))
    front = ["id_lyrics", "artist"]
    out = out[front + [c for c in out.columns if c not in front]]

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    out.to_parquet(output, index=False)
    logger.info("Wrote %d rows to %s", len(out), output)
    return {"rows": len(out), "output_file": str(output)}


def run(force: bool = False) -> dict:
    if TOP5K_PARQUET.exists() and not force:
        logger.info("%s already exists — skipping. Use --force to rebuild.", TOP5K_PARQUET)
        return {"skipped": True, "output_file": str(TOP5K_PARQUET)}
    if not EMBEDDED_PARQUET.exists():
        raise FileNotFoundError(f"Embeddings parquet not found at {EMBEDDED_PARQUET}.")
    if not TOP5000_CSV.exists():
        raise FileNotFoundError(
            f"{TOP5000_CSV} missing — run data_pipeline.step2_build_top_songs first."
        )

    aug      = _load_augmented(AUGMENTED_CSV)
    aug2pq   = _align(aug, EMBEDDED_PARQUET)
    by_tri, by_pair = _build_lookups(aug, aug2pq)
    resolved = _resolve(TOP5000_CSV, by_tri, by_pair)
    return _slice(resolved, EMBEDDED_PARQUET, TOP5K_PARQUET)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true",
                   help="Rebuild even if embedded_songs_top5000.parquet exists.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(run(force=args.force))


if __name__ == "__main__":
    main()
