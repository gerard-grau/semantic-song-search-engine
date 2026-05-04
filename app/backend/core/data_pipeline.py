"""
Generate the pre-computed 2-D projection of every embedded song.

Reads ``app/backend/data/embedded_songs.parquet`` (real Viasona embeddings)
and writes ``app/backend/data/embedded_songs_2d.parquet`` with columns
``id_lyrics, x, y``.

Usage:
    .venv/bin/python -m app.backend.core.data_pipeline                       # all songs, UMAP
    .venv/bin/python -m app.backend.core.data_pipeline --limit 5000          # only first 5 000
    .venv/bin/python -m app.backend.core.data_pipeline --limit -1            # all songs (explicit)
    .venv/bin/python -m app.backend.core.data_pipeline --method tsne         # use t-SNE
    .venv/bin/python -m app.backend.core.data_pipeline --method tsne --pca-dim 50

Methods:
    umap  — best local + global structure preservation, fast on >10 K points (default).
    tsne  — strong local clusters, weaker global distances. Combine with --pca-dim
            to pre-reduce dimensions before t-SNE for speed.
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
_OUTPUT_FILE = _DATA_DIR / "embedded_songs_2d.parquet"


def _embedding_to_array(val) -> np.ndarray:
    """Convert one parquet cell (list / np.ndarray / string) into a 1-D float array."""
    if val is None:
        return np.empty(0, dtype=np.float32)
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            return np.fromstring(s.strip("[]"), sep=",", dtype=np.float32)
        return np.empty(0, dtype=np.float32)
    return np.asarray(val, dtype=np.float32)


def _load_embeddings(limit: int | None) -> tuple[np.ndarray, np.ndarray]:
    """Return (ids, matrix) read directly from the embeddings parquet."""
    if not _EMBED_FILE.exists():
        raise FileNotFoundError(
            f"Embeddings parquet not found at {_EMBED_FILE}. "
            "Generate it with the embedding pipeline before running this."
        )

    logger.info("Reading %s …", _EMBED_FILE)
    table = pq.read_table(_EMBED_FILE, columns=["id_lyrics", "embedded_lyrics"])
    df = table.to_pandas()

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
    logger.info("Running UMAP on %d points (n_neighbors=%d, metric=cosine)…", n, n_neighbors)
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )
    return reducer.fit_transform(matrix)


def _project_tsne(matrix: np.ndarray, pca_dim: int | None) -> np.ndarray:
    from sklearn.manifold import TSNE

    if pca_dim is not None and matrix.shape[1] > pca_dim and matrix.shape[0] > pca_dim:
        logger.info("PCA pre-reduction → %d dims", pca_dim)
        matrix = PCA(n_components=pca_dim, random_state=42).fit_transform(matrix)

    n = matrix.shape[0]
    perplexity = max(5, min(30, n - 1))
    logger.info("Running t-SNE on %d points (perplexity=%d, metric=cosine)…", n, perplexity)
    tsne = TSNE(
        n_components=2,
        perplexity=perplexity,
        random_state=42,
        init="pca",
        max_iter=1000,
        metric="cosine",
    )
    return tsne.fit_transform(matrix)


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


def run_pipeline(
    limit: int | None = None,
    method: str = "umap",
    pca_dim: int | None = 50,
) -> dict:
    """
    Project every (or the first ``limit``) embedding down to 2D.

    Args:
        limit:   None or -1 for all songs; positive integer N for the first N.
        method:  "umap" (default) or "tsne".
        pca_dim: PCA pre-reduction before t-SNE; ignored for UMAP. None disables PCA.
    """
    if limit is not None and limit < 0:
        limit = None

    ids, matrix = _load_embeddings(limit)
    coords = _project_to_2d(matrix, method=method, pca_dim=pca_dim)

    out = pd.DataFrame({
        "id_lyrics": ids,
        "x":         coords[:, 0],
        "y":         coords[:, 1],
    })

    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _OUTPUT_FILE.exists():
        _OUTPUT_FILE.unlink()
        logger.info("Removed previous %s", _OUTPUT_FILE.name)
    out.to_parquet(_OUTPUT_FILE, index=False)

    logger.info("Wrote %d rows to %s (method=%s)", len(out), _OUTPUT_FILE, method)
    return {"rows": len(out), "method": method, "output_file": str(_OUTPUT_FILE)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Generate 2D song projections from real embeddings.")
    p.add_argument(
        "--limit", type=int, default=-1,
        help="Number of songs to project. -1 (default) = all songs; N = first N.",
    )
    p.add_argument(
        "--method", choices=["umap", "tsne"], default="umap",
        help="Dimensionality-reduction method (default: umap).",
    )
    p.add_argument(
        "--pca-dim", type=int, default=50,
        help="PCA pre-reduction before t-SNE (ignored for UMAP). Use 0 to disable.",
    )
    args = p.parse_args()
    pca_dim = None if args.pca_dim and args.pca_dim <= 0 else args.pca_dim
    run_pipeline(limit=args.limit, method=args.method, pca_dim=pca_dim)
