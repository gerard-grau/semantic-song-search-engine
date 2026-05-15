"""
Filter ``embedded_songs.parquet`` down to the 5000 most-viewed songs while
honouring the composite key ``(id_lyrics, artist)``.

Why this is needed:
    Some songs (collaborations, multi-artist compilations) share an
    ``id_lyrics`` but are stored as separate rows in
    ``augmented_songs.csv`` — one per artist — with one embedding row each
    in the parquet. Deduplicating purely by ``id_lyrics`` would pick the
    wrong artist's embedding for those songs.

How the alignment works:
    The embeddings parquet is row-aligned to ``augmented_songs.csv``
    (parquet rows = augmented rows with a successful embedding, in the
    same order). A two-pointer walk recovers
    ``aug_row_idx → parquet_row_idx`` and therefore
    ``(id_lyrics, artist) → parquet_row_idx``.

Inputs:
    validacio/top_5000_songs.csv                                 — popularity-ranked CSV
    /mnt/c/Users/rbarg/Desktop/augmented_songs.csv               — (id_lyrics, artist, title, album, lyrics, ...)
    /mnt/c/Users/rbarg/Desktop/embedded_songs.parquet            — full embeddings

Output:
    app/backend/data/embedded_songs_top5000.parquet
        Columns: id_lyrics, artist, plus the original embedding columns.
        At most one row per top-5000 CSV entry, in popularity order.

Usage:
    python3 -m etl.merge_top5000_with_db
    python3 -m etl.merge_top5000_with_db --augmented /path/to/augmented_songs.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

logger = logging.getLogger(__name__)

_REPO_ROOT      = Path(__file__).resolve().parent.parent
_TOP5000_CSV    = _REPO_ROOT / "validacio" / "top_5000_songs.csv"
_AUGMENTED_CSV  = Path("/mnt/c/Users/rbarg/Desktop/augmented_songs.csv")
_EMBED_PARQUET  = Path("/mnt/c/Users/rbarg/Desktop/embedded_songs.parquet")
_OUTPUT_PARQUET = _REPO_ROOT / "app" / "backend" / "data" / "embedded_songs_top5000.parquet"


def _norm_key(s) -> str:
    """Lowercase, strip accents, collapse whitespace — for fuzzy match."""
    if s is None:
        return ""
    text = unicodedata.normalize("NFKD", str(s))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower().strip())


def load_augmented(path: Path) -> pd.DataFrame:
    """Load the (id_lyrics, artist, title, album) columns from augmented_songs.csv.

    Returns the rows in file order. ``row_idx`` (0-based) is added so we can
    later align to the parquet via a two-pointer walk.
    """
    if not path.exists():
        raise FileNotFoundError(f"augmented_songs.csv not found at {path}")
    df = pd.read_csv(
        path, encoding="utf-8-sig", engine="python",
        on_bad_lines="skip",
        usecols=["id_lyrics", "artist", "title", "album"],
    )
    df["id_lyrics"] = pd.to_numeric(df["id_lyrics"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["id_lyrics"]).reset_index(drop=True)
    df["id_lyrics"] = df["id_lyrics"].astype("int64")
    df["row_idx"] = range(len(df))
    logger.info("Loaded %d augmented rows (%d unique id_lyrics).",
                len(df), df["id_lyrics"].nunique())
    return df


def align_augmented_to_parquet(
    aug: pd.DataFrame, parquet_path: Path,
) -> dict[int, int]:
    """Return ``aug_row_idx → parquet_row_idx`` by two-pointer walk over ids.

    The parquet stores one embedding row per (id_lyrics, artist) in the
    same order as augmented_songs.csv, minus 3-4k rows whose embedding
    step failed. Walking both ID sequences in lockstep — advancing the
    augmented pointer when the IDs disagree — recovers the alignment in
    one O(N) pass.
    """
    ids_pq = pq.read_table(parquet_path, columns=["id_lyrics"]).to_pandas()
    pq_ids  = ids_pq["id_lyrics"].astype("int64").to_numpy()
    aug_ids = aug["id_lyrics"].to_numpy()

    mapping: dict[int, int] = {}
    i = j = 0
    while i < len(pq_ids) and j < len(aug_ids):
        if pq_ids[i] == aug_ids[j]:
            mapping[j] = i
            i += 1
            j += 1
        else:
            j += 1

    if i != len(pq_ids):
        # If this ever happens, the parquet diverged from augmented_songs.csv
        # — refuse to write a misaligned output rather than silently mismatch
        # artists to embeddings.
        raise RuntimeError(
            f"Two-pointer alignment exhausted augmented_songs.csv with "
            f"{len(pq_ids) - i} parquet rows still unmatched at id_lyrics="
            f"{pq_ids[i] if i < len(pq_ids) else 'n/a'}. The two files no "
            f"longer share the same row order."
        )
    logger.info("Aligned %d parquet rows to augmented rows (skipped %d augmented rows).",
                len(mapping), len(aug_ids) - len(mapping))
    return mapping


def build_lookup(
    aug: pd.DataFrame, aug_to_pq: dict[int, int],
) -> tuple[dict[tuple[str, str, str], tuple[int, int, str]],
           dict[tuple[str, str], list[tuple[int, int, str, str]]]]:
    """Two lookups for the fallback chain:

    * ``by_tri``  : ``(norm_title, norm_artist, norm_album) → row triple``.
      Exact album disambiguation.
    * ``by_pair`` : ``(norm_title, norm_artist) → [(pq_idx, sid, artist, norm_album), ...]``.
      Full candidate list so the resolver can pick by substring-album
      match when the CSV's album doesn't match anything exactly.

    Only rows with a successful parquet alignment are included. The first
    occurrence wins in ``by_tri``; ``by_pair`` keeps file order for
    deterministic fallback selection.
    """
    by_tri: dict[tuple[str, str, str], tuple[int, int, str]] = {}
    by_pair: dict[tuple[str, str], list[tuple[int, int, str, str]]] = {}
    for row in aug.itertuples(index=False):
        pq_idx = aug_to_pq.get(row.row_idx)
        if pq_idx is None:
            continue
        t_key = _norm_key(row.title)
        a_key = _norm_key(row.artist)
        alb_key = _norm_key(row.album)
        triple = (pq_idx, int(row.id_lyrics), str(row.artist))
        by_tri.setdefault((t_key, a_key, alb_key), triple)
        by_pair.setdefault((t_key, a_key), []).append(
            (pq_idx, int(row.id_lyrics), str(row.artist), alb_key)
        )
    return by_tri, by_pair


def _pick_from_candidates(
    candidates: list[tuple[int, int, str, str]],
    csv_album: str,
) -> tuple[int, int, str] | None:
    """Choose the best (pq_idx, sid, artist) from a candidate list.

    Order of preference: exact album, substring match either direction,
    first candidate. Substring covers the common "Bon dia" vs.
    "Bon dia | Rock & Cat | Bon dia. Edició especial" pattern where the
    catalog album bundles the original title with reissues.
    """
    if not candidates:
        return None
    if csv_album:
        for pq_idx, sid, artist, alb_key in candidates:
            if alb_key == csv_album:
                return (pq_idx, sid, artist)
        # Substring match: catalog album bundles the CSV album (e.g., a
        # compilation titled "Bon dia | Rock & Cat | …" still contains
        # "Bon dia"). Only one-way — the reverse risks false positives
        # when the candidate album is a short word that happens to appear
        # inside an unrelated CSV album string.
        for pq_idx, sid, artist, alb_key in candidates:
            if csv_album in alb_key:
                return (pq_idx, sid, artist)
    pq_idx, sid, artist, _ = candidates[0]
    return (pq_idx, sid, artist)


_PAGE_TITLE_ALBUM_RE = re.compile(r"de l['’]àlbum\s*\"([^\"]+)\"", re.IGNORECASE)


def _album_from_page_title(page_title: str | None) -> str:
    if not page_title:
        return ""
    m = _PAGE_TITLE_ALBUM_RE.search(str(page_title))
    return m.group(1).strip() if m else ""


def resolve_top5000(
    top_csv: Path,
    by_tri: dict[tuple[str, str, str], tuple[int, int, str]],
    by_pair: dict[tuple[str, str], list[tuple[int, int, str, str]]],
) -> list[tuple[int, int, str]]:
    """Match top-5000 (title, artist, album) → ``(parquet_row_idx, id_lyrics, artist)``.

    Per CSV row, try exact (title, artist, album) first, then candidate
    selection with substring album match, then the lead-artist fallback
    for ``"Artist1, Artist2"`` CSV entries.
    """
    top = pd.read_csv(top_csv, encoding="utf-8-sig", skipinitialspace=True)
    top.columns = [c.strip().lstrip("#").strip() for c in top.columns]
    if "song_title" not in top.columns or "artist" not in top.columns:
        raise ValueError(
            f"{top_csv} must have 'song_title' and 'artist' columns. "
            f"Found: {list(top.columns)}"
        )
    has_page = "page_title" in top.columns

    resolved: list[tuple[int, int, str]] = []
    seen_pq_rows: set[int] = set()
    missing = 0
    for i in range(len(top)):
        title  = top["song_title"].iat[i]
        artist = top["artist"].iat[i]
        page   = top["page_title"].iat[i] if has_page else ""
        album  = _album_from_page_title(page)

        t_key = _norm_key(title)
        a_key = _norm_key(artist)
        alb_key = _norm_key(album)

        hit = by_tri.get((t_key, a_key, alb_key)) if alb_key else None
        if hit is None:
            hit = _pick_from_candidates(by_pair.get((t_key, a_key), []), alb_key)
        if hit is None and "," in str(artist or ""):
            first_artist = _norm_key(str(artist).split(",", 1)[0])
            if alb_key:
                hit = by_tri.get((t_key, first_artist, alb_key))
            if hit is None:
                hit = _pick_from_candidates(by_pair.get((t_key, first_artist), []), alb_key)

        if hit is None:
            missing += 1
            continue
        pq_idx, _sid, _real_artist = hit
        if pq_idx in seen_pq_rows:
            continue
        seen_pq_rows.add(pq_idx)
        resolved.append(hit)
    logger.info(
        "Resolved %d / %d top-5000 entries to a (id_lyrics, artist) pair "
        "(%d unmatched).",
        len(resolved), len(top), missing,
    )
    return resolved


def slice_parquet(
    resolved: list[tuple[int, int, str]],
    embed_parquet: Path,
    output: Path,
) -> dict:
    """Read only the requested parquet rows; preserve popularity order.

    PyArrow's ``take`` is row-index based and reads the whole table, so
    for a 5k-of-83k filter we stream batches and keep rows whose absolute
    row index is in the target set. That keeps peak memory well below
    loading the full 5 GB parquet.
    """
    if not embed_parquet.exists():
        raise FileNotFoundError(f"Embeddings parquet not found at {embed_parquet}.")
    if not resolved:
        raise ValueError("Empty resolved list — refusing to write an empty parquet.")

    wanted_rows  = {row_idx for row_idx, _sid, _art in resolved}
    artist_by_pq = {row_idx: artist for row_idx, _sid, artist in resolved}
    rank_by_pq   = {row_idx: rank for rank, (row_idx, _s, _a) in enumerate(resolved)}

    pf = pq.ParquetFile(embed_parquet)
    chunks: list[pd.DataFrame] = []
    seen_rows = 0
    cursor = 0  # absolute row index across batches
    for batch in pf.iter_batches(batch_size=10_000):
        end = cursor + batch.num_rows
        in_window = [i for i in range(cursor, end) if i in wanted_rows]
        if in_window:
            df = batch.to_pandas()
            local_offsets = [i - cursor for i in in_window]
            sub = df.iloc[local_offsets].copy()
            sub["_pq_row"] = in_window
            chunks.append(sub)
            seen_rows += len(in_window)
        cursor = end
        if seen_rows == len(wanted_rows):
            break

    if not chunks or seen_rows != len(wanted_rows):
        raise RuntimeError(
            f"Found {seen_rows} / {len(wanted_rows)} requested parquet rows. "
            "Check that the embeddings parquet matches augmented_songs.csv."
        )

    out = pd.concat(chunks, ignore_index=True)
    out["artist"]   = out["_pq_row"].map(artist_by_pq)
    out["_rank"]    = out["_pq_row"].map(rank_by_pq)
    out = out.sort_values("_rank").drop(columns=["_pq_row", "_rank"]).reset_index(drop=True)

    # Move id_lyrics + artist to the front for readability; embedding cols
    # come after.
    front = ["id_lyrics", "artist"]
    rest  = [c for c in out.columns if c not in front]
    out = out[front + rest]

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    out.to_parquet(output, index=False)
    logger.info("Wrote %d rows to %s", len(out), output)
    return {"rows": len(out), "output_file": str(output)}


def main() -> None:
    p = argparse.ArgumentParser(description="Filter embeddings to top-5000 by (id, artist).")
    p.add_argument("--top-csv",       type=Path, default=_TOP5000_CSV)
    p.add_argument("--augmented",     type=Path, default=_AUGMENTED_CSV)
    p.add_argument("--embed-parquet", type=Path, default=_EMBED_PARQUET)
    p.add_argument("--output",        type=Path, default=_OUTPUT_PARQUET)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    aug = load_augmented(args.augmented)
    aug_to_pq = align_augmented_to_parquet(aug, args.embed_parquet)
    by_tri, by_pair = build_lookup(aug, aug_to_pq)
    logger.info(
        "Built lookup over %d aligned rows (triples=%d, distinct title+artist=%d).",
        sum(1 for _ in aug_to_pq), len(by_tri), len(by_pair),
    )
    resolved = resolve_top5000(args.top_csv, by_tri, by_pair)
    result = slice_parquet(resolved, args.embed_parquet, args.output)
    print(f"Done: {result['rows']} rows → {result['output_file']}")


if __name__ == "__main__":
    main()
