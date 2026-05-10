"""
Data-pipeline utilities — precompute artefacts that the API consumes.

Two outputs:

* ``embedded_songs_2d.parquet`` (cols: id_lyrics, x, y) — full-dataset
  2D projection of every embedding. Generated with UMAP (default) or
  t-SNE.
* ``songs_meta.parquet`` — a clean metadata snapshot for every song
  whose id is in ``embedded_songs.parquet``. Replaces the slow row-by-
  row streaming of ``augmented_songs.csv`` + ``cancons.csv`` at API
  start-up (and on every first ``/api/songs`` call).

Usage:
    .venv/bin/python -m app.backend.core.data_pipeline                       # all artefacts
    .venv/bin/python -m app.backend.core.data_pipeline --skip-meta           # only 2D
    .venv/bin/python -m app.backend.core.data_pipeline --only-meta           # only metadata snapshot
    .venv/bin/python -m app.backend.core.data_pipeline --method tsne --pca-dim 50
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.decomposition import PCA

logger = logging.getLogger(__name__)

_DATA_DIR    = Path(__file__).parent.parent / "data"
_EMBED_FILE  = _DATA_DIR / "embedded_songs.parquet"
_OUTPUT_2D   = _DATA_DIR / "embedded_songs_2d.parquet"
_OUTPUT_META = _DATA_DIR / "songs_meta.parquet"


# ---------------------------------------------------------------------------
# 2-D projection
# ---------------------------------------------------------------------------

def _embedding_to_array(val) -> np.ndarray:
    if val is None:
        return np.empty(0, dtype=np.float32)
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            return np.fromstring(s.strip("[]"), sep=",", dtype=np.float32)
        return np.empty(0, dtype=np.float32)
    return np.asarray(val, dtype=np.float32)


def _load_embeddings(limit: int | None) -> tuple[np.ndarray, np.ndarray]:
    if not _EMBED_FILE.exists():
        raise FileNotFoundError(
            f"Embeddings parquet not found at {_EMBED_FILE}. "
            "Generate it with the embedding pipeline before running this."
        )
    logger.info("Reading %s …", _EMBED_FILE)
    df = pq.read_table(_EMBED_FILE, columns=["id_lyrics", "embedded_lyrics"]).to_pandas()
    if limit is not None:
        df = df.head(limit)
    if df.empty:
        raise ValueError("Embeddings parquet is empty.")
    ids = df["id_lyrics"].astype("int64").to_numpy()
    matrix = np.vstack([_embedding_to_array(v) for v in df["embedded_lyrics"]])
    logger.info("Loaded %d embeddings of dim %d", matrix.shape[0], matrix.shape[1])
    return ids, matrix


def _project_umap(matrix: np.ndarray) -> np.ndarray:
    try:
        import umap  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "umap-learn is not installed. Run `pip install umap-learn` "
            "or use --method tsne."
        ) from exc
    n = matrix.shape[0]
    n_neighbors = max(2, min(15, n - 1))
    logger.info("Running UMAP on %d points (n_neighbors=%d)…", n, n_neighbors)
    return umap.UMAP(
        n_components=2, n_neighbors=n_neighbors, min_dist=0.1,
        metric="cosine", random_state=42,
    ).fit_transform(matrix)


def _project_tsne(matrix: np.ndarray, pca_dim: int | None) -> np.ndarray:
    from sklearn.manifold import TSNE
    if pca_dim is not None and matrix.shape[1] > pca_dim and matrix.shape[0] > pca_dim:
        logger.info("PCA pre-reduction → %d dims", pca_dim)
        matrix = PCA(n_components=pca_dim, random_state=42).fit_transform(matrix)
    n = matrix.shape[0]
    perplexity = max(5, min(30, n - 1))
    logger.info("Running t-SNE on %d points…", n)
    return TSNE(
        n_components=2, perplexity=perplexity, random_state=42,
        init="pca", max_iter=1000, metric="cosine",
    ).fit_transform(matrix)


def _project_to_2d(matrix: np.ndarray, method: str, pca_dim: int | None) -> np.ndarray:
    n = matrix.shape[0]
    if n <= 1:
        return np.zeros((n, 2), dtype=np.float32)
    method = method.lower()
    if method == "umap":
        coords = _project_umap(matrix)
    elif method == "tsne":
        coords = _project_tsne(matrix, pca_dim=pca_dim)
    else:
        raise ValueError(f"Unknown method: {method!r}. Use 'umap' or 'tsne'.")
    return coords.astype(np.float32)


def run_projection(
    limit: int | None = None,
    method: str = "umap",
    pca_dim: int | None = 50,
) -> dict:
    """Project every embedding down to 2D and write the parquet."""
    if limit is not None and limit < 0:
        limit = None
    ids, matrix = _load_embeddings(limit)
    coords = _project_to_2d(matrix, method=method, pca_dim=pca_dim)
    out = pd.DataFrame({
        "id_lyrics": ids,
        "x":         coords[:, 0],
        "y":         coords[:, 1],
    })
    _OUTPUT_2D.parent.mkdir(parents=True, exist_ok=True)
    if _OUTPUT_2D.exists():
        _OUTPUT_2D.unlink()
    out.to_parquet(_OUTPUT_2D, index=False)
    logger.info("Wrote %d rows to %s (method=%s)", len(out), _OUTPUT_2D, method)
    return {"rows": len(out), "method": method, "output_file": str(_OUTPUT_2D)}


# Backwards-compatible alias used elsewhere.
def run_pipeline(*args, **kwargs):
    return run_projection(*args, **kwargs)


# ---------------------------------------------------------------------------
# Metadata snapshot
# ---------------------------------------------------------------------------

def _parquet_ids() -> set[int]:
    table = pq.read_table(_EMBED_FILE, columns=["id_lyrics"])
    return {int(x) for x in table.column("id_lyrics").to_pylist()}


def run_metadata_snapshot() -> dict:
    """
    Read augmented_songs.csv + cancons.csv once (cleanly), keep only the
    rows whose id_lyrics is in ``embedded_songs.parquet``, and write a
    compact parquet that the API loads directly.
    """
    # Avoid a circular import — data_loader uses the snapshot we're writing.
    from app.backend.core.data_loader import _load_metadata_for_ids

    ids = _parquet_ids()
    logger.info("Building metadata snapshot for %d ids …", len(ids))
    songs = _load_metadata_for_ids(ids)
    if not songs:
        raise RuntimeError("No metadata rows produced — check the CSVs.")

    df = pd.DataFrame(songs)
    if "embedding" in df.columns:
        df = df.drop(columns=["embedding"])
    _OUTPUT_META.parent.mkdir(parents=True, exist_ok=True)
    if _OUTPUT_META.exists():
        _OUTPUT_META.unlink()
    df.to_parquet(_OUTPUT_META, index=False)
    logger.info("Wrote %d rows to %s", len(df), _OUTPUT_META)
    return {"rows": len(df), "output_file": str(_OUTPUT_META)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Generate API artefacts from embeddings.")
    p.add_argument("--limit",  type=int, default=-1, help="Number of songs to project (-1 = all).")
    p.add_argument("--method", choices=["umap", "tsne"], default="umap")
    p.add_argument("--pca-dim", type=int, default=50, help="PCA pre-reduction for t-SNE (0 disables).")
    p.add_argument("--skip-meta", action="store_true", help="Skip metadata snapshot.")
    p.add_argument("--only-meta", action="store_true", help="Only build the metadata snapshot.")
    args = p.parse_args()

    pca_dim = None if args.pca_dim and args.pca_dim <= 0 else args.pca_dim

    if not args.only_meta:
        run_projection(limit=args.limit, method=args.method, pca_dim=pca_dim)
    if not args.skip_meta:
        run_metadata_snapshot()
