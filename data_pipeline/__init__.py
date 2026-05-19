"""Offline data pipeline — generates every artefact the API consumes.

Inputs (must exist before running):
  * ``app/backend/data/augmented_songs.csv``     — full song table
  * ``app/backend/data/embedded_songs.parquet``  — per-field bge-m3 embeddings
  * ``validacio/entrances_exits.csv``            — GA4 popularity export
  * ``.env``                                     — MariaDB credentials (optional)

Outputs (written into ``app/backend/data/``):
  * ``cancons.csv``, ``grups.csv``, ``noticies.csv``  — from DB if reachable
  * ``top_5000_songs.csv``                            — with genre column
  * ``embedded_songs_top5000.parquet``                — embeddings for visible set
  * ``embedded_songs_genres.parquet``                 — per-song one-hot genre
  * ``songs_meta.parquet``                            — UI metadata snapshot
  * ``embedded_songs_2d.parquet``                     — UMAP/t-SNE 2D layout

Run everything with::

    python -m data_pipeline.execute_all
"""
