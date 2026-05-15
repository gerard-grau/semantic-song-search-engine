"""
Apply ``app/backend/data/artist_genres.csv`` to every song in the catalogue.

Joins the curated artist→genre table onto ``songs_meta.parquet`` (which carries
``id`` + ``artist`` for every embedded song), produces a one-hot 11-d profile
per song, and overwrites ``app/backend/data/embedded_songs_genres.parquet`` so
that:

* The 2D projection (``data_pipeline.run_projection``) clusters by the new
  genres.
* The genre bonus in ``embeddings.filter_*`` rewards same-genre matches.
* ``songs_meta.parquet`` rebuild picks up the new ``genre`` label.

Output schema (same as the zero-shot version, just 11-d instead of 8-d):
    id_lyrics    (int64)
    genre        (str)        — slug from the 11-label taxonomy
    genre_scores (list[float]) — one-hot vector aligned with ``GENRES`` order

Songs whose artist isn't in ``artist_genres.csv`` (e.g. blank artist field)
fall back to ``--default-genre`` (default: ``folk``) and a one-hot at that
position. Count is logged so it's auditable.

Usage:
    .venv/bin/python -m etl.apply_artist_genres
    .venv/bin/python -m etl.apply_artist_genres --default-genre indie
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from etl.build_artist_genres import GENRES

logger = logging.getLogger(__name__)

_REPO_ROOT      = Path(__file__).resolve().parent.parent
_DATA_DIR       = _REPO_ROOT / "app" / "backend" / "data"
_ARTIST_GENRES  = _DATA_DIR / "artist_genres.csv"
_SONGS_META     = _DATA_DIR / "songs_meta.parquet"
_OUTPUT         = _DATA_DIR / "embedded_songs_genres.parquet"


def _one_hot(slug: str) -> np.ndarray:
    """Build a one-hot float32 vector for ``slug`` aligned with ``GENRES``."""
    v = np.zeros(len(GENRES), dtype=np.float32)
    v[GENRES.index(slug)] = 1.0
    return v


def apply(default_genre: str = "folk") -> dict:
    if default_genre not in GENRES:
        raise ValueError(f"default genre {default_genre!r} not in taxonomy {GENRES}")
    if not _ARTIST_GENRES.exists():
        raise FileNotFoundError(
            f"{_ARTIST_GENRES} missing — run `python -m etl.build_artist_genres` first."
        )
    if not _SONGS_META.exists():
        raise FileNotFoundError(
            f"{_SONGS_META} missing — run `python -m app.backend.core.data_pipeline --only-meta` first."
        )

    logger.info("Reading %s …", _ARTIST_GENRES)
    ag = pd.read_csv(_ARTIST_GENRES)
    ag["artist"] = ag["artist"].astype(str).str.strip()
    artist_to_genre = dict(zip(ag["artist"], ag["genre"]))
    logger.info("Loaded %d artist→genre mappings.", len(artist_to_genre))

    logger.info("Reading %s …", _SONGS_META)
    meta = pq.read_table(_SONGS_META, columns=["id", "artist"]).to_pandas()
    meta["artist"] = meta["artist"].astype(str).str.strip()
    meta["id"]     = meta["id"].astype("int64")
    logger.info(
        "Loaded %d rows from metadata snapshot (%d unique song ids).",
        len(meta), meta["id"].nunique(),
    )

    # Songs_meta splits collabs into one row per artist. For each song id,
    # prefer the row whose artist is in artist_genres.csv so we don't lose
    # labels just because songs_meta listed a different artist of the same
    # song first. Stable sort + drop_duplicates keeps the labeled row.
    meta["is_labeled"] = meta["artist"].isin(artist_to_genre)
    meta = (meta.sort_values(["id", "is_labeled"], ascending=[True, False], kind="stable")
                .drop_duplicates(subset=["id"], keep="first")
                .drop(columns=["is_labeled"])
                .reset_index(drop=True))
    logger.info("Deduplicated to %d rows (one per song id).", len(meta))

    matched = meta["artist"].isin(artist_to_genre)
    n_matched   = int(matched.sum())
    n_unmatched = int((~matched).sum())
    logger.info(
        "Matched %d / %d songs by artist (%d fall back to default=%s).",
        n_matched, len(meta), n_unmatched, default_genre,
    )

    meta["genre"] = meta["artist"].map(artist_to_genre).fillna(default_genre)

    # Pre-compute one-hot vectors per genre slug to avoid building one per row.
    one_hots = {slug: _one_hot(slug) for slug in GENRES}
    meta["genre_scores"] = meta["genre"].map(one_hots)

    out = pd.DataFrame({
        "id_lyrics":    meta["id"],
        "genre":        meta["genre"],
        "genre_scores": meta["genre_scores"],
    })

    if _OUTPUT.exists():
        _OUTPUT.unlink()
    out.to_parquet(_OUTPUT, index=False)

    counts = out["genre"].value_counts()
    logger.info("Wrote %d rows to %s", len(out), _OUTPUT)
    logger.info("Genre distribution:\n%s", counts.to_string())
    return {
        "rows":          len(out),
        "matched":       n_matched,
        "unmatched":     n_unmatched,
        "default_genre": default_genre,
        "output_file":   str(_OUTPUT),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Apply artist_genres.csv → embedded_songs_genres.parquet.")
    p.add_argument("--default-genre", default="folk",
                   help="Fallback for songs whose artist isn't in artist_genres.csv (default: folk).")
    args = p.parse_args()
    apply(default_genre=args.default_genre)
