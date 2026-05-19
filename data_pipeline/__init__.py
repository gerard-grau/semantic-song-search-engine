"""Offline data pipeline — generates every artefact the API consumes.

Data layout::

    app/backend/data/raw/        — externally-sourced inputs
    app/backend/data/processed/  — pipeline-derived artefacts

Inputs (must exist in ``app/backend/data/raw/`` before running):
  * ``augmented_songs.csv``       — full song table (manual export)
  * ``embedded_songs.parquet``    — per-field bge-m3 embeddings
                                    (produced by ``ml/embeddings/preembedding.py``)
  * ``entrances_exits.csv``       — GA4 popularity export

  Plus, outside ``app/backend/data/``:
  * ``.env``                      — MariaDB credentials (optional)

Step 1 also writes to ``app/backend/data/raw/`` because its contents are
DB dumps rather than computed artefacts:
  * ``cancons.csv``, ``grups.csv``, ``noticies.csv``

Outputs (written into ``app/backend/data/processed/``):
  * ``top_5000_songs.csv``                  — with genre column
  * ``embedded_songs_top5000.parquet``      — embeddings for visible set
  * ``embedded_songs_genres.parquet``       — per-song one-hot genre
  * ``songs_meta.parquet``                  — UI metadata snapshot
  * ``embedded_songs_2d.parquet``           — UMAP/t-SNE 2D layout

Run everything with::

    python -m data_pipeline.execute_all
"""
