"""
Step 2 — build ``top_5000_songs.csv`` from the GA4 entrances/exits export.

The CSV produced here drives every downstream step:
  * Step 3 uses it to select which embeddings to keep.
  * Step 4 reads the ``genre`` column to build the per-song one-hot parquet.
  * Step 5 joins the ``genre`` column onto the metadata snapshot.

The output columns are: ``#, song_title, artist, page_title, views, genre``.
The ``genre`` value comes from ``data_pipeline._genres.RANK_TO_GENRE`` —
human-curated labels (six categories) previously split across the ten
``validacio/_add_genre_partNN.py`` scripts.
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import pandas as pd

import config

from ._genres import RANK_TO_GENRE
from ._paths import ENTRANCES_CSV, TOP5000_CSV

logger = logging.getLogger(__name__)


def _read_ga4(path: Path) -> pd.DataFrame:
    """Parse a GA4 export — skips the leading ``#`` comment block and the
    blank rows GA4 inserts between sections."""
    rows: list[list[str]] = []
    header: list[str] | None = None
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#"):
                continue
            if header is None:
                header = row
                continue
            if len(row) == len(header):
                rows.append(row)
    if header is None:
        raise ValueError(f"{path} has no header row.")
    return pd.DataFrame(rows, columns=header)


def _filter_songs(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only Viasona song pages (a song page title looks like
    ``"<song>, de l'àlbum \"<album>\" (<artist>) - Viasona"``)."""
    df = df.rename(columns={df.columns[0]: "title"})
    df["Views"]    = pd.to_numeric(df["Views"],    errors="coerce")
    df["Sessions"] = pd.to_numeric(df["Sessions"], errors="coerce")
    df["title"]    = df["title"].astype(str).str.strip()
    df = df[df["title"] != ""].copy()

    t = df["title"]
    is_song = (
        t.str.contains(r"de l['’]àlbum", case=False, na=False)
        & t.str.contains(r"\(.+\)", na=False)
        & t.str.contains(r"-\s*Viasona$", case=False, na=False)
    )
    not_song = t.str.contains(
        r"tota la música|agenda|concerts|notícies|artistes|grups|discografia|"
        r"llistat|llista|cerca|home|inici|cançons en català|enviar lletra|"
        r"vídeos|videoclips|biografia|entrevista|especial",
        case=False, na=False,
    )
    songs = df[is_song & ~not_song].copy()
    songs["song_title"] = songs["title"].str.extract(r"^(.*?), de", expand=False)
    songs["artist"]     = songs["title"].str.extract(
        r"\(([^)]+)\)[^)]*-\s*Viasona$", expand=False
    )
    return songs


def run(top_n: int = config.PIPELINE_TOP_N, force: bool = False) -> dict:
    """Build top_5000_songs.csv with genre column. Idempotent."""
    if TOP5000_CSV.exists() and not force:
        logger.info("%s already exists — skipping. Use --force to rebuild.", TOP5000_CSV)
        return {"skipped": True, "output_file": str(TOP5000_CSV)}

    if not ENTRANCES_CSV.exists():
        raise FileNotFoundError(
            f"GA4 export not found at {ENTRANCES_CSV}. "
            "Place the Viasona entrances/exits export there before running."
        )

    raw = _read_ga4(ENTRANCES_CSV)
    songs = _filter_songs(raw)
    top = songs.sort_values("Views", ascending=False).head(top_n).reset_index(drop=True)

    export = top[["song_title", "artist", "title", "Views"]].copy()
    export.insert(0, "#", range(1, len(export) + 1))
    export = export.rename(columns={"title": "page_title", "Views": "views"})

    # Apply human-curated genres by rank. Songs beyond the curated set fall
    # back to ``folk`` (default) so the schema stays consistent.
    export["genre"] = [RANK_TO_GENRE.get(int(rank), "folk") for rank in export["#"]]

    TOP5000_CSV.parent.mkdir(parents=True, exist_ok=True)
    export.to_csv(TOP5000_CSV, index=False, encoding="utf-8-sig")
    logger.info(
        "Wrote %d rows (%d with curated genre) to %s",
        len(export), int(export["#"].le(len(RANK_TO_GENRE)).sum()), TOP5000_CSV,
    )
    return {"rows": len(export), "output_file": str(TOP5000_CSV)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top-n", type=int, default=config.PIPELINE_TOP_N,
                   help=f"How many top songs to keep (config default: {config.PIPELINE_TOP_N}).")
    p.add_argument("--force", action="store_true",
                   help="Rebuild even if top_5000_songs.csv already exists.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(run(top_n=args.top_n, force=args.force))


if __name__ == "__main__":
    main()
