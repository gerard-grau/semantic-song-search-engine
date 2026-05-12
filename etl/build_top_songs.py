"""
Build ``app/backend/data/top_5000_songs.csv`` from a GA4 Entrances/Exits export.

The CSV produced here drives ``data_pipeline.py``: it determines the 5000
songs that get projected to 2D and shown in the visualization, and the
5000 whose embeddings are kept in ``embedded_songs_top5000.parquet`` for
fast similarity scoring.

Inputs:
    validacio/entrances_exits.csv  — GA4 export with one row per page.

Output:
    app/backend/data/top_5000_songs.csv — columns: #, song_title, artist,
    page_title, views.

Usage:
    .venv/bin/python -m etl.build_top_songs
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_REPO_ROOT   = Path(__file__).resolve().parent.parent
_GA4_CSV     = _REPO_ROOT / "validacio" / "entrances_exits.csv"
_OUTPUT_CSV  = _REPO_ROOT / "app" / "backend" / "data" / "top_5000_songs.csv"


def get_top_viewed_songs(csv_path: Path, top_n: int = 5000) -> pd.DataFrame:
    """Parse a GA4 'Entrances/Exits' export and return the top N most viewed songs."""
    rows: list[list[str]] = []
    header: list[str] | None = None

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            if header is None:
                header = row
                continue
            if len(row) == len(header):
                rows.append(row)

    df = pd.DataFrame(rows, columns=header)
    df = df.rename(columns={df.columns[0]: "title"})

    df["Views"]    = pd.to_numeric(df["Views"], errors="coerce")
    df["Sessions"] = pd.to_numeric(df["Sessions"], errors="coerce")
    df["title"]    = df["title"].astype(str).str.strip()
    df = df[df["title"] != ""].copy()

    title_series = df["title"]

    is_song = (
        title_series.str.contains(r"de l['’]àlbum", case=False, na=False)
        & title_series.str.contains(r"\(.+\)", na=False)
        & title_series.str.contains(r"-\s*Viasona$", case=False, na=False)
    )
    not_song = title_series.str.contains(
        r"tota la música|agenda|concerts|notícies|artistes|grups|discografia|"
        r"llistat|llista|cerca|home|inici|cançons en català|enviar lletra|"
        r"vídeos|videoclips|biografia|entrevista|especial",
        case=False, na=False,
    )

    songs_df = df[is_song & ~not_song].copy()
    songs_df["song_title"] = songs_df["title"].str.extract(r"^(.*?), de", expand=False)
    songs_df["artist"]     = songs_df["title"].str.extract(
        r"\(([^)]+)\)[^)]*-\s*Viasona$", expand=False
    )

    return songs_df.sort_values("Views", ascending=False).head(top_n)


def build_top_songs_csv(
    ga4_csv: Path = _GA4_CSV,
    output_csv: Path = _OUTPUT_CSV,
    top_n: int = 5000,
) -> Path:
    if not ga4_csv.exists():
        raise FileNotFoundError(f"GA4 export not found at {ga4_csv}")

    top = get_top_viewed_songs(ga4_csv, top_n=top_n)
    export_df = top[["song_title", "artist", "title", "Views"]].copy()
    export_df.insert(0, "#", range(1, len(export_df) + 1))
    export_df = export_df.rename(columns={"title": "page_title", "Views": "views"})

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    export_df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    logger.info("Wrote %d rows to %s", len(export_df), output_csv)
    return output_csv


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = build_top_songs_csv()
    print(f"Successfully saved results to {out}")
