"""
Single entry point — run every step of the data pipeline.

Inputs required in ``app/backend/data/``:
  * augmented_songs.csv
  * embedded_songs.parquet

Inputs required at the repo root:
  * validacio/entrances_exits.csv
  * .env (optional, but recommended — needed to refresh cancons/grups/noticies.csv)

After this script runs successfully you can launch the API with
``uvicorn app.backend.api.main:app`` and everything will be served from
precomputed artefacts — no per-request projection, no per-request DB query.

Each step is idempotent: re-running this script only does the work that
hasn't been done yet. Pass ``--force`` to redo everything.

Usage:
    python -m data_pipeline.execute_all
    python -m data_pipeline.execute_all --force
    python -m data_pipeline.execute_all --method tsne --alpha-genre 3.0
"""

from __future__ import annotations

import argparse
import logging
import time

import config

from . import (
    step1_fetch_catalogue_csvs as s1,
    step2_build_top_songs       as s2,
    step3_filter_top5000_embeddings as s3,
    step4_build_genres_parquet  as s4,
    step5_build_meta            as s5,
    step6_project_2d            as s6,
)

logger = logging.getLogger("data_pipeline")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true",
                   help="Rebuild every output, even ones already on disk.")
    p.add_argument("--method", choices=["umap", "tsne", "pca_umap"],
                   default=config.PIPELINE_PROJECTION_METHOD,
                   help=f"2D projection backend (config default: {config.PIPELINE_PROJECTION_METHOD}).")
    p.add_argument("--pca-dim", type=int, default=config.PIPELINE_PCA_DIM,
                   help=f"PCA pre-reduction for t-SNE / pca_umap (0 disables; config default: {config.PIPELINE_PCA_DIM}).")
    p.add_argument("--genre-mode", choices=["soft", "onehot", "none"],
                   default=config.PIPELINE_GENRE_MODE,
                   help=f"How to use the genre block in the 2D layout (config default: {config.PIPELINE_GENRE_MODE}).")
    p.add_argument("--alpha-genre", type=float, default=config.PIPELINE_ALPHA_GENRE,
                   help=f"Genre weight in squared distance is alpha² × text (config default: {config.PIPELINE_ALPHA_GENRE}).")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

    pca_dim = None if args.pca_dim and args.pca_dim <= 0 else args.pca_dim

    steps = [
        ("step1: catalogue CSVs from DB",      lambda: s1.run(force=args.force)),
        ("step2: top_5000_songs.csv + genres", lambda: s2.run(force=args.force)),
        ("step3: embedded_songs_top5000",      lambda: s3.run(force=args.force)),
        ("step4: embedded_songs_genres",       lambda: s4.run(force=args.force)),
        ("step5: songs_meta.parquet",          lambda: s5.run(force=args.force)),
        ("step6: embedded_songs_2d",           lambda: s6.run(
            method=args.method, pca_dim=pca_dim,
            genre_mode=args.genre_mode, alpha_genre=args.alpha_genre,
            force=args.force,
        )),
    ]

    for label, fn in steps:
        logger.info("──── %s ────", label)
        t0 = time.perf_counter()
        result = fn()
        logger.info("%s done in %.1fs → %s", label, time.perf_counter() - t0, result)

    logger.info("All artefacts up to date.")


if __name__ == "__main__":
    main()
