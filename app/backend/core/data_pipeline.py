"""
Data-pipeline utilities — precompute artefacts that the API consumes.

Three outputs:

* ``embedded_songs_top5000.parquet`` — all per-field 1024-D embeddings
  for the 5000 most-viewed songs (selected from ``top_5000_songs.csv``).
  This is what the API reads at filter time: cosine similarity is
  computed against these 5000 rows, never against the full 80k catalog.
* ``embedded_songs_2d.parquet`` (cols: id_lyrics, x, y) — 2D projection
  of those same 5000 embeddings. Generated with UMAP (default) or
  t-SNE. Optionally augmented with a per-song genre block so songs of
  the same genre cluster together in the 2-D layout.
* ``songs_meta.parquet`` — a clean metadata snapshot for every song
  whose id is in ``embedded_songs.parquet``. Replaces the slow row-by-
  row streaming of ``augmented_songs.csv`` + ``cancons.csv`` at API
  start-up (and on every first ``/api/songs`` call). The ``genre`` field
  is populated from ``embedded_songs_genres.parquet`` if it exists.

Genre augmentation
------------------
When ``embedded_songs_genres.parquet`` is present, layout vectors are built as

    layout[i] = concat( unit(text[i]), alpha_genre · unit(genre_block[i]) )

With both halves unit-norm per row, ``alpha_genre`` directly controls how much
genre dominates the projection: contribution to squared distance is exactly
``alpha_genre²`` times that of text. Default ``alpha_genre = 2.0`` makes genre
roughly 4× the influence of text — visible clusters without erasing within-
genre semantics. Set ``--genre-mode none`` to disable.

Usage:
    .venv/bin/python -m app.backend.core.data_pipeline                              # all artefacts
    .venv/bin/python -m app.backend.core.data_pipeline --skip-meta                  # only 2D
    .venv/bin/python -m app.backend.core.data_pipeline --only-meta                  # only metadata snapshot
    .venv/bin/python -m app.backend.core.data_pipeline --method tsne --pca-dim 50
    .venv/bin/python -m app.backend.core.data_pipeline --method pca_umap --pca-dim 4
    .venv/bin/python -m app.backend.core.data_pipeline --alpha-genre 3.0            # stronger genre clustering
    .venv/bin/python -m app.backend.core.data_pipeline --genre-mode onehot          # hard genre buckets
    .venv/bin/python -m app.backend.core.data_pipeline --genre-mode none            # original behaviour
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
from sklearn.decomposition import PCA

logger = logging.getLogger(__name__)

_DATA_DIR      = Path(__file__).parent.parent / "data"
_EMBED_FILE    = _DATA_DIR / "embedded_songs.parquet"
_GENRES_FILE   = _DATA_DIR / "embedded_songs_genres.parquet"
_TOP5000_CSV   = _DATA_DIR / "top_5000_songs.csv"
_OUTPUT_TOP5K  = _DATA_DIR / "embedded_songs_top5000.parquet"
_OUTPUT_2D     = _DATA_DIR / "embedded_songs_2d.parquet"
_OUTPUT_META   = _DATA_DIR / "songs_meta.parquet"
_AUGMENTED_CSV = _DATA_DIR / "augmented_songs.csv"

# Default knobs for the augmented layout
_DEFAULT_GENRE_MODE  = "soft"   # one of: soft, onehot, none
_DEFAULT_ALPHA_GENRE = 2.0      # genre influence on squared distance is alpha²/(1+alpha²)
                                # alpha=2 → 80% genre / 20% text. Lower softens
                                # the cluster geometry but blurs genre separation.


# ---------------------------------------------------------------------------
# Top-5000 resolution + embeddings snapshot
# ---------------------------------------------------------------------------

def _norm_key(s) -> str:
    """Lowercase, strip accents, collapse whitespace — for fuzzy title/artist match."""
    if s is None:
        return ""
    text = str(s)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _load_title_artist_index() -> dict[tuple[str, str], int]:
    """Map ``(norm_title, norm_artist) → id_lyrics``.

    Prefers ``songs_meta.parquet`` (clean UTF-8, fast). Falls back to the
    raw ``augmented_songs.csv`` so the pipeline can still resolve ids the
    first time it runs, before the metadata snapshot has been built.
    """
    if _OUTPUT_META.exists():
        df = pq.read_table(_OUTPUT_META, columns=["id", "title", "artist"]).to_pandas()
        df = df.rename(columns={"id": "id_lyrics"})
    elif _AUGMENTED_CSV.exists():
        df = pd.read_csv(
            _AUGMENTED_CSV, encoding="utf-8-sig",
            usecols=["id_lyrics", "title", "artist"],
            on_bad_lines="skip",
        )
    else:
        raise FileNotFoundError(
            f"Neither {_OUTPUT_META} nor {_AUGMENTED_CSV} exist — cannot "
            "resolve top-5000 song ids."
        )
    df["id_lyrics"] = pd.to_numeric(df["id_lyrics"], errors="coerce")
    df = df.dropna(subset=["id_lyrics"])
    out: dict[tuple[str, str], int] = {}
    for sid, title, artist in zip(df["id_lyrics"], df["title"], df["artist"]):
        key = (_norm_key(title), _norm_key(artist))
        # First occurrence wins — duplicate (title, artist) pairs are rare.
        out.setdefault(key, int(sid))
    return out


def resolve_top5000_ids() -> list[int]:
    """Read ``top_5000_songs.csv`` and return id_lyrics in popularity order.

    Songs that can't be matched by (title, artist) — typo, alt spelling,
    missing from catalog — are skipped with a warning. The returned list is
    typically slightly under 5000 in practice.
    """
    if not _TOP5000_CSV.exists():
        raise FileNotFoundError(
            f"Top-5000 CSV not found at {_TOP5000_CSV}. "
            "Generate it with `python -m etl.build_top_songs`."
        )
    top = pd.read_csv(_TOP5000_CSV, encoding="utf-8-sig", skipinitialspace=True)
    top.columns = [c.strip().lstrip("#").strip() for c in top.columns]
    if "song_title" not in top.columns or "artist" not in top.columns:
        raise ValueError(
            f"{_TOP5000_CSV} must have 'song_title' and 'artist' columns. "
            f"Found: {list(top.columns)}"
        )

    index = _load_title_artist_index()
    # Secondary index: (norm_title, first_norm_artist) — picks up multi-artist
    # collaborations in the CSV ("Artist1, Artist2") that the catalog stores
    # under just the lead artist.
    first_artist_index: dict[tuple[str, str], int] = {}
    for (t, a), sid in index.items():
        first_artist_index.setdefault((t, a), sid)
    ids: list[int] = []
    seen: set[int] = set()
    missing = 0
    for title, artist in zip(top["song_title"], top["artist"]):
        t_key = _norm_key(title)
        a_key = _norm_key(artist)
        sid = index.get((t_key, a_key))
        if sid is None and "," in str(artist or ""):
            first_artist = str(artist).split(",", 1)[0]
            sid = first_artist_index.get((t_key, _norm_key(first_artist)))
        if sid is None:
            missing += 1
            continue
        if sid in seen:
            continue
        seen.add(sid)
        ids.append(sid)
    logger.info(
        "Resolved %d / %d top-5000 songs to id_lyrics (%d unmatched).",
        len(ids), len(top), missing,
    )
    return ids


def run_top5000_embeddings(ids: list[int]) -> dict:
    """Filter ``embedded_songs.parquet`` down to the top-5000 ids.

    Streams the source parquet to avoid loading the full ~80k × 5-field
    matrix into memory at once. The output preserves the popularity order
    given by ``ids``.
    """
    if not _EMBED_FILE.exists():
        raise FileNotFoundError(f"Embeddings parquet not found at {_EMBED_FILE}.")
    if not ids:
        raise ValueError("Empty id list — refusing to write an empty top-5000 parquet.")

    wanted = {int(i) for i in ids}
    pf = pq.ParquetFile(_EMBED_FILE)
    chunks: list[pd.DataFrame] = []
    seen: set[int] = set()
    for batch in pf.iter_batches(batch_size=10_000):
        df = batch.to_pandas()
        df["id_lyrics"] = df["id_lyrics"].astype("int64")
        sub = df[df["id_lyrics"].isin(wanted)]
        if not sub.empty:
            chunks.append(sub)
            seen.update(sub["id_lyrics"].tolist())
        if len(seen) == len(wanted):
            break

    if not chunks:
        raise RuntimeError("No top-5000 ids matched any row in embedded_songs.parquet.")

    out = pd.concat(chunks, ignore_index=True)
    # Dedupe and reorder to match the popularity ranking in ``ids``. Some
    # rows in embedded_songs.parquet share an id_lyrics (re-embeds, dupes);
    # keep just the first occurrence so each visible song has exactly one row.
    out = out.drop_duplicates(subset=["id_lyrics"], keep="first")
    order = {sid: rank for rank, sid in enumerate(ids)}
    out["_rank"] = out["id_lyrics"].map(order)
    out = out.sort_values("_rank").drop(columns=["_rank"]).reset_index(drop=True)

    _OUTPUT_TOP5K.parent.mkdir(parents=True, exist_ok=True)
    if _OUTPUT_TOP5K.exists():
        _OUTPUT_TOP5K.unlink()
    out.to_parquet(_OUTPUT_TOP5K, index=False)
    missing = len(wanted) - len(out)
    if missing > 0:
        logger.warning(
            "%d / %d top-5000 ids were absent from %s — embedded_songs may be stale.",
            missing, len(wanted), _EMBED_FILE.name,
        )
    logger.info("Wrote %d rows to %s", len(out), _OUTPUT_TOP5K)
    return {"rows": len(out), "output_file": str(_OUTPUT_TOP5K)}


# ---------------------------------------------------------------------------
# 2-D projection
# ---------------------------------------------------------------------------

def _embedding_to_array(val) -> np.ndarray:
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


def _load_embeddings() -> tuple[np.ndarray, np.ndarray]:
    """Load lyrics embeddings for the top-5000 set (in popularity order)."""
    source = _OUTPUT_TOP5K if _OUTPUT_TOP5K.exists() else _EMBED_FILE
    if not source.exists():
        raise FileNotFoundError(
            f"Embeddings parquet not found at {source}. "
            "Run the embedding pipeline / top-5000 step before projecting."
        )
    logger.info("Reading %s …", source)
    df = pq.read_table(source, columns=["id_lyrics", "embedded_lyrics"]).to_pandas()
    if df.empty:
        raise ValueError(f"{source} is empty.")
    ids = df["id_lyrics"].astype("int64").to_numpy()
    matrix = np.vstack([_embedding_to_array(v) for v in df["embedded_lyrics"]])
    logger.info("Loaded %d embeddings of dim %d", matrix.shape[0], matrix.shape[1])
    return ids, matrix


def _row_normalize(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise each row in place-safe way; zero rows stay zero."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1.0
    return matrix / norms


def _load_genre_block(ids: np.ndarray, mode: str) -> np.ndarray | None:
    """
    Load the per-song genre block aligned with ``ids``.

    Returns an ``(N, G)`` float32 matrix or ``None`` when augmentation is off
    or the genre parquet is missing. Each row is L2-normalised so the
    ``alpha_genre`` knob is interpretable regardless of how peaky the
    underlying softmax was.

    ``mode``:
      - "soft"   — use the softmax profile directly.
      - "onehot" — collapse to a hard one-hot from the argmax.
      - "none"   — disable augmentation.
    """
    if mode == "none":
        return None
    if not _GENRES_FILE.exists():
        logger.warning(
            "Genre parquet not found at %s — projection runs without "
            "augmentation. Generate it with `python -m ml.embeddings.classify_genres`.",
            _GENRES_FILE,
        )
        return None
    if mode not in ("soft", "onehot"):
        raise ValueError(f"Unknown genre_mode: {mode!r}. Use soft/onehot/none.")

    logger.info("Reading %s (mode=%s) …", _GENRES_FILE, mode)
    gdf = pq.read_table(_GENRES_FILE).to_pandas()
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
        else:  # soft
            block[i] = profile

    if missing:
        logger.warning("Genre block missing for %d / %d ids (left as zeros).",
                       missing, len(ids))
    return _row_normalize(block)


def _prepare_layout_vectors(
    text: np.ndarray,
    genre_block: np.ndarray | None,
    alpha_genre: float,
    pca_dim: int | None,
) -> np.ndarray:
    """
    Build the input matrix fed to the manifold-learning step.

    Steps (in order):
      1. Optionally PCA-reduce *text only*. We deliberately do PCA before
         concatenation so the genre block — which is only a few dims wide —
         never gets discarded by PCA's variance criterion.
      2. Re-normalise rows so ``alpha_genre`` keeps its clean interpretation:
         with both blocks unit-norm, genre's contribution to squared distance
         is exactly ``alpha_genre²`` times that of text.
      3. Concatenate ``[text | alpha_genre * genre_block]``.
    """
    text = text.astype(np.float32, copy=False)

    if pca_dim is not None and 0 < pca_dim < text.shape[1] and text.shape[0] > pca_dim:
        logger.info("PCA on text: %d → %d dims", text.shape[1], pca_dim)
        text = PCA(n_components=pca_dim, random_state=42).fit_transform(text).astype(np.float32)
        text = _row_normalize(text)

    if genre_block is None or alpha_genre <= 0:
        return text

    logger.info(
        "Concatenating genre block (G=%d, alpha=%.2f) → genre contributes "
        "%.0f%% of squared distance.",
        genre_block.shape[1], alpha_genre,
        100 * alpha_genre ** 2 / (1 + alpha_genre ** 2),
    )
    return np.concatenate([text, alpha_genre * genre_block], axis=1).astype(np.float32)


def _project_umap(matrix: np.ndarray, metric: str) -> np.ndarray:
    try:
        import umap  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "umap-learn is not installed. Run `pip install umap-learn` "
            "or use --method tsne."
        ) from exc
    n = matrix.shape[0]
    n_neighbors = max(2, min(15, n - 1))
    logger.info("Running UMAP on %d × %d points (n_neighbors=%d, metric=%s)…",
                n, matrix.shape[1], n_neighbors, metric)
    return umap.UMAP(
        n_components=2, n_neighbors=n_neighbors, min_dist=0.1,
        metric=metric, random_state=42,
    ).fit_transform(matrix)


def _project_tsne(matrix: np.ndarray) -> np.ndarray:
    from sklearn.manifold import TSNE
    n = matrix.shape[0]
    perplexity = max(5, min(30, n - 1))
    logger.info("Running t-SNE on %d × %d points…", n, matrix.shape[1])
    return TSNE(
        n_components=2, perplexity=perplexity, random_state=42,
        init="pca", max_iter=1000, metric="cosine",
    ).fit_transform(matrix)


def _project_to_2d(
    matrix: np.ndarray,
    method: str,
    augmented: bool,
) -> np.ndarray:
    """Dispatch the manifold-learning step on a pre-prepared matrix.

    ``augmented`` only affects metric choice for the ``pca_umap`` path, where
    the unaugmented historical default was Euclidean. When we augment, we
    re-normalise rows after PCA and switch to cosine so the alpha² ratio is
    preserved consistently with the other methods.
    """
    n = matrix.shape[0]
    if n <= 1:
        return np.zeros((n, 2), dtype=np.float32)
    method = method.lower()
    if method == "umap":
        coords = _project_umap(matrix, metric="cosine")
    elif method == "tsne":
        coords = _project_tsne(matrix)
    elif method in ("pca_umap", "pca+umap", "pcaumap"):
        coords = _project_umap(matrix, metric="cosine" if augmented else "euclidean")
    else:
        raise ValueError(
            f"Unknown method: {method!r}. Use 'umap', 'tsne' or 'pca_umap'."
        )
    return coords.astype(np.float32)


def run_projection(
    method: str = "umap",
    pca_dim: int | None = 50,
    genre_mode: str = _DEFAULT_GENRE_MODE,
    alpha_genre: float = _DEFAULT_ALPHA_GENRE,
) -> dict:
    """Project the top-5000 embeddings down to 2D and write the parquet.

    With ``genre_mode != 'none'`` and ``embedded_songs_genres.parquet``
    present, the projection is computed on augmented vectors so songs of
    the same genre cluster together. See module docstring for the math.
    """
    ids, matrix = _load_embeddings()
    genre_block = _load_genre_block(ids, mode=genre_mode)

    # PCA only applies to methods that benefit from it (t-SNE and pca_umap).
    effective_pca_dim = pca_dim if method.lower() in ("tsne", "pca_umap", "pca+umap", "pcaumap") else None
    prepared = _prepare_layout_vectors(
        matrix, genre_block, alpha_genre=alpha_genre, pca_dim=effective_pca_dim,
    )
    coords = _project_to_2d(
        prepared, method=method, augmented=genre_block is not None,
    )

    out = pd.DataFrame({
        "id_lyrics": ids,
        "x":         coords[:, 0],
        "y":         coords[:, 1],
    })
    _OUTPUT_2D.parent.mkdir(parents=True, exist_ok=True)
    if _OUTPUT_2D.exists():
        _OUTPUT_2D.unlink()
    out.to_parquet(_OUTPUT_2D, index=False)
    logger.info(
        "Wrote %d rows to %s (method=%s, genre_mode=%s, alpha=%.2f)",
        len(out), _OUTPUT_2D, method,
        genre_mode if genre_block is not None else "none",
        alpha_genre,
    )
    return {
        "rows":         len(out),
        "method":       method,
        "genre_mode":   genre_mode if genre_block is not None else "none",
        "alpha_genre":  alpha_genre,
        "output_file":  str(_OUTPUT_2D),
    }


# Backwards-compatible alias used elsewhere.
def run_pipeline(*args, **kwargs):
    return run_projection(*args, **kwargs)


# ---------------------------------------------------------------------------
# Metadata snapshot
# ---------------------------------------------------------------------------

def _parquet_ids() -> set[int]:
    table = pq.read_table(_EMBED_FILE, columns=["id_lyrics"])
    return {int(x) for x in table.column("id_lyrics").to_pylist()}


def _load_genre_labels() -> dict[int, str]:
    """Map ``id_lyrics → genre slug`` from the classification parquet (if any)."""
    if not _GENRES_FILE.exists():
        return {}
    gdf = pq.read_table(_GENRES_FILE, columns=["id_lyrics", "genre"]).to_pandas()
    gdf["id_lyrics"] = gdf["id_lyrics"].astype("int64")
    return {int(i): str(g) for i, g in zip(gdf["id_lyrics"], gdf["genre"])}


def run_metadata_snapshot() -> dict:
    """
    Read augmented_songs.csv + cancons.csv once (cleanly), keep only the
    rows whose id_lyrics is in ``embedded_songs.parquet``, and write a
    compact parquet that the API loads directly. If
    ``embedded_songs_genres.parquet`` exists, its ``genre`` column is joined
    onto each song so the frontend can colour by genre.
    """
    # Avoid a circular import — data_loader uses the snapshot we're writing.
    from app.backend.core.data_loader import _load_metadata_for_ids

    ids = _parquet_ids()
    logger.info("Building metadata snapshot for %d ids …", len(ids))
    songs = _load_metadata_for_ids(ids)
    if not songs:
        raise RuntimeError("No metadata rows produced — check the CSVs.")

    genre_map = _load_genre_labels()
    if genre_map:
        for s in songs:
            s["genre"] = genre_map.get(int(s["id"]), s.get("genre", "") or "")
        logger.info("Joined genre on %d / %d songs from %s",
                    sum(1 for s in songs if s.get("genre")), len(songs), _GENRES_FILE)
    else:
        logger.info("No %s — songs_meta.parquet leaves genre empty.", _GENRES_FILE.name)

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
    p.add_argument("--method", choices=["umap", "tsne", "pca_umap"], default="umap")
    p.add_argument("--pca-dim", type=int, default=50,
                   help="PCA pre-reduction for t-SNE / pca_umap (0 disables).")
    p.add_argument("--genre-mode", choices=["soft", "onehot", "none"],
                   default=_DEFAULT_GENRE_MODE,
                   help="How to use the genre block. 'soft' uses the softmax "
                        "profile, 'onehot' the argmax label, 'none' disables.")
    p.add_argument("--alpha-genre", type=float, default=_DEFAULT_ALPHA_GENRE,
                   help="Genre weight in squared distance is alpha² × text. "
                        "Set 0 to disable. (default: %(default)s)")
    p.add_argument("--skip-meta", action="store_true", help="Skip metadata snapshot.")
    p.add_argument("--only-meta", action="store_true", help="Only build the metadata snapshot.")
    p.add_argument("--skip-top5000", action="store_true",
                   help="Reuse existing embedded_songs_top5000.parquet without rebuilding it.")
    args = p.parse_args()

    pca_dim = None if args.pca_dim and args.pca_dim <= 0 else args.pca_dim

    # Metadata snapshot first — needed by resolve_top5000_ids() for fast,
    # clean (title, artist) → id_lyrics matching.
    if not args.skip_meta:
        run_metadata_snapshot()

    if args.only_meta:
        raise SystemExit(0)

    if not args.skip_top5000:
        top_ids = resolve_top5000_ids()
        run_top5000_embeddings(top_ids)

    run_projection(
        method=args.method, pca_dim=pca_dim,
        genre_mode=args.genre_mode, alpha_genre=args.alpha_genre,
    )
