"""Shared filesystem paths for the data pipeline.

Layout::

    app/backend/data/
    ├── raw/         — external data the pipeline consumes (manual drops,
    │                  DB dumps from step1). Re-fetching these is expensive
    │                  or requires network/DB access.
    └── processed/   — every artefact the pipeline computes from raw/.
                       Safe to delete and rebuild with ``execute_all.py``.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR      = REPO_ROOT / "app" / "backend" / "data"
RAW_DIR       = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
ENV_FILE      = REPO_ROOT / ".env"

# Raw inputs — externally sourced, not produced by pipeline transforms.
AUGMENTED_CSV    = RAW_DIR / "augmented_songs.csv"
EMBEDDED_PARQUET = RAW_DIR / "embedded_songs.parquet"
CANCONS_CSV      = RAW_DIR / "cancons.csv"   # DB dump (step1 just extracts)
GRUPS_CSV        = RAW_DIR / "grups.csv"     # DB dump
NOTICIES_CSV     = RAW_DIR / "noticies.csv"  # DB dump
ENTRANCES_CSV    = RAW_DIR / "entrances_exits.csv"   # GA4 export

# Processed outputs — derived artefacts written by steps 2-6.
TOP5000_CSV     = PROCESSED_DIR / "top_5000_songs.csv"
TOP5K_PARQUET   = PROCESSED_DIR / "embedded_songs_top5000.parquet"
GENRES_PARQUET  = PROCESSED_DIR / "embedded_songs_genres.parquet"
META_PARQUET    = PROCESSED_DIR / "songs_meta.parquet"
PROJECTION_2D   = PROCESSED_DIR / "embedded_songs_2d.parquet"
