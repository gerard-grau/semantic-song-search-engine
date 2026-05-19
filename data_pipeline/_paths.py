"""Shared filesystem paths for the data pipeline."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR  = REPO_ROOT / "app" / "backend" / "data"
ENV_FILE  = REPO_ROOT / ".env"

# Inputs
AUGMENTED_CSV    = DATA_DIR / "augmented_songs.csv"
EMBEDDED_PARQUET = DATA_DIR / "embedded_songs.parquet"
ENTRANCES_CSV    = REPO_ROOT / "validacio" / "entrances_exits.csv"

# Generated CSVs
CANCONS_CSV   = DATA_DIR / "cancons.csv"
GRUPS_CSV     = DATA_DIR / "grups.csv"
NOTICIES_CSV  = DATA_DIR / "noticies.csv"
TOP5000_CSV   = DATA_DIR / "top_5000_songs.csv"

# Generated parquets
TOP5K_PARQUET    = DATA_DIR / "embedded_songs_top5000.parquet"
GENRES_PARQUET   = DATA_DIR / "embedded_songs_genres.parquet"
META_PARQUET     = DATA_DIR / "songs_meta.parquet"
PROJECTION_2D    = DATA_DIR / "embedded_songs_2d.parquet"
