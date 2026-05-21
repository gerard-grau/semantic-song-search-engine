"""
Step 6 — 2D projection of the top-5000 embeddings.

Outputs ``embedded_songs_2d.parquet`` with columns ``id_lyrics, x, y``.

Genre augmentation
------------------
When ``embedded_songs_genres.parquet`` is present, layout vectors are built as

    layout[i] = concat( unit(text[i]), alpha_genre · unit(genre_block[i]) )

With both halves unit-norm per row, ``alpha_genre`` directly controls how much
genre dominates the projection: contribution to squared distance is exactly
``alpha_genre²`` times that of text. Default ``alpha_genre = 2.0`` makes genre
roughly 4× the influence of text — visible clusters without erasing within-
genre semantics. Set ``--genre-mode none`` to disable.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.decomposition import PCA

import config

from ._paths import GENRES_PARQUET, PROJECTION_2D, TOP5K_PARQUET

logger = logging.getLogger(__name__)


def _emb_to_array(val) -> np.ndarray:
    if val is None:
        return np.empty(0, dtype=np.float32)
    if isinstance(val, bytes):
        val = val.decode("utf-8")
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            return np.fromstring(s.strip("[]"), sep=",", dtype=np.float32)
        return np.empty(0, dtype=np.float32)
    return np.asarray(val, dtype=np.float32)


def _row_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1.0
    return matrix / norms


def _load_embeddings(source: Path) -> tuple[np.ndarray, np.ndarray]:
    if not source.exists():
        raise FileNotFoundError(f"Embeddings parquet not found at {source}.")
    logger.info("Reading %s …", source)
    df = pq.read_table(source, columns=["id_lyrics", "embedded_lyrics"]).to_pandas()
    if df.empty:
        raise ValueError(f"{source} is empty.")
    ids    = df["id_lyrics"].astype("int64").to_numpy()
    matrix = np.vstack([_emb_to_array(v) for v in df["embedded_lyrics"]])
    logger.info("Loaded %d embeddings, dim %d", matrix.shape[0], matrix.shape[1])
    return ids, matrix


def _load_genre_block(ids: np.ndarray, mode: str) -> np.ndarray | None:
    if mode == "none":
        return None
    if not GENRES_PARQUET.exists():
        logger.warning("No %s — projecting without genre augmentation.", GENRES_PARQUET)
        return None
    if mode not in ("soft", "onehot"):
        raise ValueError(f"Unknown genre_mode {mode!r}.")

    logger.info("Reading %s (mode=%s) …", GENRES_PARQUET, mode)
    gdf = pq.read_table(GENRES_PARQUET).to_pandas()
    gdf["id_lyrics"] = gdf["id_lyrics"].astype("int64")
    first = np.asarray(gdf["genre_scores"].iloc[0], dtype=np.float32)
    G = int(first.shape[0])
    index = {int(i): np.asarray(s, dtype=np.float32)
             for i, s in zip(gdf["id_lyrics"], gdf["genre_scores"])}

    block = np.zeros((len(ids), G), dtype=np.float32)
    missing = 0
    for i, sid in enumerate(ids):
        profile = index.get(int(sid))
        if profile is None:
            missing += 1
            continue
        if mode == "onehot":
            block[i, int(profile.argmax())] = 1.0
        else:
            block[i] = profile
    if missing:
        logger.warning("Genre block missing for %d / %d ids.", missing, len(ids))
    return _row_normalize(block)


def _prepare(text: np.ndarray, genre_block: np.ndarray | None,
             alpha_genre: float, pca_dim: int | None) -> np.ndarray:
    text = text.astype(np.float32, copy=False)
    if pca_dim is not None and 0 < pca_dim < text.shape[1] and text.shape[0] > pca_dim:
        logger.info("PCA on text: %d → %d dims", text.shape[1], pca_dim)
        text = PCA(n_components=pca_dim, random_state=42).fit_transform(text).astype(np.float32)
        text = _row_normalize(text)
    if genre_block is None or alpha_genre <= 0:
        return text
    logger.info("Concatenating genre block (G=%d, alpha=%.2f) → genre %.0f%% of dist²",
                genre_block.shape[1], alpha_genre,
                100 * alpha_genre ** 2 / (1 + alpha_genre ** 2))
    return np.concatenate([text, alpha_genre * genre_block], axis=1).astype(np.float32)


def _umap(matrix: np.ndarray, metric: str) -> np.ndarray:
    try:
        import umap  # type: ignore
    except ImportError as exc:
        raise ImportError("umap-learn not installed; `pip install umap-learn` or use --method tsne.") from exc
    n = matrix.shape[0]
    n_neighbors = max(2, min(15, n - 1))
    logger.info("UMAP on %d × %d (n_neighbors=%d, metric=%s) …",
                n, matrix.shape[1], n_neighbors, metric)
    return umap.UMAP(
        n_components=2, n_neighbors=n_neighbors, min_dist=0.1,
        metric=metric, random_state=42,
    ).fit_transform(matrix)


def _tsne(matrix: np.ndarray) -> np.ndarray:
    from sklearn.manifold import TSNE
    n = matrix.shape[0]
    perplexity = max(5, min(30, n - 1))
    logger.info("t-SNE on %d × %d …", n, matrix.shape[1])
    return TSNE(
        n_components=2, perplexity=perplexity, random_state=42,
        init="pca", max_iter=1000, metric="cosine",
    ).fit_transform(matrix)


def _project(matrix: np.ndarray, method: str, augmented: bool) -> np.ndarray:
    n = matrix.shape[0]
    if n <= 1:
        return np.zeros((n, 2), dtype=np.float32)
    method = method.lower()
    if method == "umap":
        coords = _umap(matrix, metric="cosine")
    elif method == "tsne":
        coords = _tsne(matrix)
    elif method in ("pca_umap", "pca+umap", "pcaumap"):
        coords = _umap(matrix, metric="cosine" if augmented else "euclidean")
    else:
        raise ValueError(f"Unknown method {method!r}. Use umap, tsne, pca_umap.")
    return coords.astype(np.float32)


def run(method: str = config.PIPELINE_PROJECTION_METHOD,
        pca_dim: int | None = config.PIPELINE_PCA_DIM,
        genre_mode: str = config.PIPELINE_GENRE_MODE,
        alpha_genre: float = config.PIPELINE_ALPHA_GENRE,
        force: bool = False) -> dict:
    if PROJECTION_2D.exists() and not force:
        logger.info("%s already exists — skipping. Use --force to rebuild.", PROJECTION_2D)
        return {"skipped": True, "output_file": str(PROJECTION_2D)}

    ids, matrix = _load_embeddings(TOP5K_PARQUET)
    genre_block = _load_genre_block(ids, mode=genre_mode)
    effective_pca = pca_dim if method.lower() in ("tsne", "pca_umap", "pca+umap", "pcaumap") else None
    prepared = _prepare(matrix, genre_block, alpha_genre=alpha_genre, pca_dim=effective_pca)
    coords   = _project(prepared, method=method, augmented=genre_block is not None)

    df = pd.DataFrame({"id_lyrics": ids, "x": coords[:, 0], "y": coords[:, 1]})
    PROJECTION_2D.parent.mkdir(parents=True, exist_ok=True)
    if PROJECTION_2D.exists():
        PROJECTION_2D.unlink()
    df.to_parquet(PROJECTION_2D, index=False)
    logger.info("Wrote %d rows to %s (method=%s, genre_mode=%s, alpha=%.2f)",
                len(df), PROJECTION_2D, method,
                genre_mode if genre_block is not None else "none", alpha_genre)
    return {
        "rows":         len(df),
        "method":       method,
        "genre_mode":   genre_mode if genre_block is not None else "none",
        "alpha_genre":  alpha_genre,
        "output_file":  str(PROJECTION_2D),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--method", choices=["umap", "tsne", "pca_umap"],
                   default=config.PIPELINE_PROJECTION_METHOD,
                   help=f"Projection backend (config default: {config.PIPELINE_PROJECTION_METHOD}).")
    p.add_argument("--pca-dim", type=int, default=config.PIPELINE_PCA_DIM,
                   help=f"PCA pre-reduction for t-SNE / pca_umap (0 disables; config default: {config.PIPELINE_PCA_DIM}).")
    p.add_argument("--genre-mode", choices=["soft", "onehot", "none"],
                   default=config.PIPELINE_GENRE_MODE,
                   help=f"Genre block usage in layout (config default: {config.PIPELINE_GENRE_MODE}).")
    p.add_argument("--alpha-genre", type=float, default=config.PIPELINE_ALPHA_GENRE,
                   help=f"Genre weight multiplier (config default: {config.PIPELINE_ALPHA_GENRE}).")
    p.add_argument("--force", action="store_true",
                   help="Rebuild even if embedded_songs_2d.parquet exists.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pca_dim = None if args.pca_dim and args.pca_dim <= 0 else args.pca_dim
    print(run(method=args.method, pca_dim=pca_dim,
              genre_mode=args.genre_mode, alpha_genre=args.alpha_genre,
              force=args.force))


if __name__ == "__main__":
    main()
