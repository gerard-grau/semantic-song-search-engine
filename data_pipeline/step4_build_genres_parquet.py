"""
Step 4 — build ``embedded_songs_genres.parquet`` from the curated genres
in ``top_5000_songs.csv``.

Schema (matches what ``data_loader._load_genre_profiles`` and
``data_pipeline.run_projection`` expect):
    id_lyrics    (int64)
    genre        (str)         — slug from data_pipeline._genres.GENRES
    genre_scores (list[float]) — one-hot vector aligned with GENRES order

Each row in ``embedded_songs_top5000.parquet`` is joined to the matching
(title, artist) pair in ``top_5000_songs.csv`` to recover its rank →
genre. No re-classification is run — the labels come straight from the
curated dict at ``data_pipeline._genres.RANK_TO_GENRE``.
"""

from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ._genres import GENRES
from ._paths import GENRES_PARQUET, TOP5000_CSV, TOP5K_PARQUET

logger = logging.getLogger(__name__)


def _norm_key(s) -> str:
    if s is None:
        return ""
    text = unicodedata.normalize("NFKD", str(s))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower().strip())


def _one_hot_table() -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for i, slug in enumerate(GENRES):
        v = np.zeros(len(GENRES), dtype=np.float32)
        v[i] = 1.0
        out[slug] = v
    return out


def run(default_genre: str = "folk", force: bool = False) -> dict:
    if GENRES_PARQUET.exists() and not force:
        logger.info("%s already exists — skipping. Use --force to rebuild.", GENRES_PARQUET)
        return {"skipped": True, "output_file": str(GENRES_PARQUET)}
    if default_genre not in GENRES:
        raise ValueError(f"default_genre {default_genre!r} not in taxonomy {GENRES}")
    if not TOP5K_PARQUET.exists():
        raise FileNotFoundError(
            f"{TOP5K_PARQUET} missing — run step3_filter_top5000_embeddings first."
        )
    if not TOP5000_CSV.exists():
        raise FileNotFoundError(
            f"{TOP5000_CSV} missing — run step2_build_top_songs first."
        )

    top = pd.read_csv(TOP5000_CSV, encoding="utf-8-sig", skipinitialspace=True)
    top.columns = [c.strip().lstrip("#").strip() for c in top.columns]
    if "genre" not in top.columns:
        raise ValueError(
            f"{TOP5000_CSV} is missing the 'genre' column. Rebuild with step2 first."
        )
    # Two lookup tables: by (title, artist) for the precise case, and by
    # title-only as a fallback for parquets that don't carry artist.
    genre_by_pair: dict[tuple[str, str], str] = {}
    genre_by_title: dict[str, str] = {}
    for _, r in top.iterrows():
        t_key = _norm_key(r["song_title"])
        a_key = _norm_key(r["artist"])
        genre_by_pair.setdefault((t_key, a_key), str(r["genre"]))
        genre_by_title.setdefault(t_key, str(r["genre"]))

    # The new step3 writes ``id_lyrics`` + ``artist``; the legacy parquet from
    # the old pipeline has only ``id_lyrics``. Detect the schema and adapt.
    pq_schema = pq.ParquetFile(TOP5K_PARQUET).schema_arrow.names
    cols = ["id_lyrics"]
    if "artist" in pq_schema:
        cols.append("artist")
    ids_df = pq.read_table(TOP5K_PARQUET, columns=cols).to_pandas()
    has_artist = "artist" in ids_df.columns

    # We need song titles to key into the CSV. Pull them from augmented_songs.
    from ._paths import AUGMENTED_CSV
    # augmented_songs.csv is latin-1 with a stray leading 0xff (UTF-16 BOM
    # remnant). Strip that off the first header so usecols can resolve it.
    aug = pd.read_csv(
        AUGMENTED_CSV, encoding="latin-1", engine="python",
        on_bad_lines="skip",
    )
    aug.columns = [re.sub(r"^[^\w]+", "", c, flags=re.ASCII).lstrip("﻿") for c in aug.columns]
    aug = aug[["id_lyrics", "artist", "title"]].copy()
    aug["id_lyrics"] = pd.to_numeric(aug["id_lyrics"], errors="coerce").astype("Int64")
    aug = aug.dropna(subset=["id_lyrics"])
    aug["id_lyrics"] = aug["id_lyrics"].astype("int64")
    title_by_id_artist: dict[tuple[int, str], str] = {}
    title_by_id: dict[int, str] = {}
    for sid, ar, ti in zip(aug["id_lyrics"], aug["artist"], aug["title"]):
        title_by_id_artist[(int(sid), _norm_key(ar))] = _norm_key(ti)
        title_by_id.setdefault(int(sid), _norm_key(ti))

    one_hot = _one_hot_table()
    rows: list[dict] = []
    matched = 0
    for i in range(len(ids_df)):
        sid = int(ids_df["id_lyrics"].iat[i])
        artist = ids_df["artist"].iat[i] if has_artist else None
        a_key = _norm_key(artist) if artist is not None else ""
        title_key = title_by_id_artist.get((sid, a_key)) if has_artist else None
        if not title_key:
            title_key = title_by_id.get(sid, "")
        if has_artist and a_key:
            genre = genre_by_pair.get((title_key, a_key))
        else:
            genre = None
        if genre is None:
            genre = genre_by_title.get(title_key, default_genre)
        if genre not in one_hot:
            genre = default_genre
        else:
            matched += 1
        rows.append({
            "id_lyrics":    sid,
            "genre":        genre,
            "genre_scores": one_hot[genre],
        })

    df = pd.DataFrame(rows)
    GENRES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    if GENRES_PARQUET.exists():
        GENRES_PARQUET.unlink()
    df.to_parquet(GENRES_PARQUET, index=False)

    counts = df["genre"].value_counts()
    logger.info("Wrote %d rows to %s (%d matched the curated genres CSV).",
                len(df), GENRES_PARQUET, matched)
    logger.info("Genre distribution:\n%s", counts.to_string())
    return {
        "rows":         len(df),
        "matched":      matched,
        "fallback":     len(df) - matched,
        "output_file":  str(GENRES_PARQUET),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--default-genre", default="folk",
                   help="Fallback genre for songs not matched in top_5000_songs.csv.")
    p.add_argument("--force", action="store_true",
                   help="Rebuild even if embedded_songs_genres.parquet exists.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(run(default_genre=args.default_genre, force=args.force))


if __name__ == "__main__":
    main()
