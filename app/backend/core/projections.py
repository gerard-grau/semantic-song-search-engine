"""
Projection module — computes t-SNE 2D and 3D from k-dimensional embeddings.

The full-dataset projections are cached so that a "reset" is instant.
Any filtered subset triggers a fresh t-SNE computation.
"""

from __future__ import annotations

import numpy as np
from sklearn.manifold import MDS, TSNE

from app.backend.core.data_loader import load_all_songs

# ---------------------------------------------------------------------------
# Cache for full-dataset projections (computed once, reused on reset)
# ---------------------------------------------------------------------------
_cached_all_2d: list[dict] | None = None
_cached_all_3d: list[dict] | None = None


def _songs_to_matrix(songs: list[dict]) -> np.ndarray:
    """Extract the k-dim embedding from each song into an (n, k) numpy array."""
    return np.array([s["embedding"] for s in songs], dtype=np.float64)


def _run_tsne(matrix: np.ndarray, n_components: int) -> np.ndarray:
    """
    Run t-SNE on an (n, k) matrix and return (n, n_components) coordinates.

    Handles edge cases:
      - n == 1  → return origin
      - n < 4   → use PCA init and perplexity = max(1, n-1)
      - n >= 4  → standard t-SNE with perplexity = min(30, n-1)
    """
    n = matrix.shape[0]
    if n <= 1:
        return np.zeros((n, n_components))

    perplexity = min(30, n - 1)
    perplexity = max(1, perplexity)

    init = "pca" if n >= n_components else "random"

    tsne = TSNE(
        n_components=n_components,
        perplexity=perplexity,
        random_state=42,
        init=init,
        max_iter=500,
    )
    return tsne.fit_transform(matrix)


def _build_points(songs: list[dict], coords: np.ndarray, dims: int) -> list[dict]:
    """Combine song metadata with projected coordinates."""
    points = []
    for i, song in enumerate(songs):
        p = {
            "id": song["id"],
            "x": round(float(coords[i, 0]), 4),
            "y": round(float(coords[i, 1]), 4),
            "title": song["title"],
            "artist": song["artist"],
            "genre": song["genre"],
            "role": song.get("role", "neighbor"),
        }
        if dims == 3:
            p["z"] = round(float(coords[i, 2]), 4)
        points.append(p)
    return points


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_tsne_2d(songs: list[dict]) -> list[dict]:
    """
    Compute t-SNE 2D projections from the k-dimensional 'embedding' field.

    Args:
        songs: list of song dicts, each must contain 'embedding' (list[float]).

    Returns:
        List of {id, x, y, title, artist, genre}.
    """
    if not songs:
        return []
    matrix = _songs_to_matrix(songs)
    coords = _run_tsne(matrix, n_components=2)
    return _build_points(songs, coords, dims=2)


def compute_tsne_3d(songs: list[dict]) -> list[dict]:
    """
    Compute t-SNE 3D projections from the k-dimensional 'embedding' field.

    Args:
        songs: list of song dicts, each must contain 'embedding' (list[float]).

    Returns:
        List of {id, x, y, z, title, artist, genre}.
    """
    if not songs:
        return []
    matrix = _songs_to_matrix(songs)
    coords = _run_tsne(matrix, n_components=3)
    return _build_points(songs, coords, dims=3)


def get_all_projections_2d() -> list[dict]:
    """
    Get cached 2D projections for ALL songs.
    Computes t-SNE on first call, then returns the cache.
    """
    global _cached_all_2d
    if _cached_all_2d is None:
        _cached_all_2d = compute_tsne_2d(load_all_songs())
    return _cached_all_2d


def get_all_projections_3d() -> list[dict]:
    """
    Get cached 3D projections for ALL songs.
    Computes t-SNE on first call, then returns the cache.
    """
    global _cached_all_3d
    if _cached_all_3d is None:
        _cached_all_3d = compute_tsne_3d(load_all_songs())
    return _cached_all_3d


def compute_neighborhood_2d(
    songs: list[dict],
    focal_id: int,
    previous_song_id: int | None = None,
    previous_positions: dict[int, tuple[float, float]] | None = None,
) -> list[dict]:
    """
    Compute 2D layout for a neighborhood using metric MDS on cosine distances.

    The focal song is always placed at the origin.  The single rotational
    degree of freedom of the plane is used to preserve the travel angle:
    the previous focal song appears in the direction the user "came from",
    giving a coherent sense of motion through the graph.

    Algorithm
    ---------
    1. Build an (n × n) cosine-distance matrix from L2-normalised embeddings.
    2. Run metric MDS (dissimilarity="precomputed") to get 2D coordinates.
    3. Translate so the focal song is at the origin.
    4. Scale so the 75th-percentile non-focal distance equals 1.0.
    5. If previous positions are available, rotate the plane so that the
       previous focal song lands at angle (theta_travel + π), where
       theta_travel is atan2(focal_old - prev_old) — the direction the user
       travelled in the previous layout.

    Args:
        songs:              Neighborhood songs, each with 'embedding' and 'role'.
        focal_id:           ID of the focal (centre) song.
        previous_song_id:   ID of the song navigated from.
        previous_positions: Dict mapping song id → (x, y) from the prior step.

    Returns:
        List of point dicts {id, x, y, title, artist, genre, role}.
    """
    if not songs:
        return []

    n = len(songs)
    if n == 1:
        return _build_points(songs, np.zeros((1, 2)), dims=2)

    # ── 1. Cosine distance matrix ────────────────────────────────────
    matrix = _songs_to_matrix(songs)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normed = matrix / norms
    cos_sim = np.clip(normed @ normed.T, -1.0, 1.0)
    dist_mat = (1.0 - cos_sim).astype(np.float64)
    np.fill_diagonal(dist_mat, 0.0)

    # ── 2. Metric MDS ────────────────────────────────────────────────
    n_init = 4 if n <= 30 else 1
    mds = MDS(
        n_components=2,
        metric_mds=True,
        metric="precomputed",
        init="random",
        random_state=42,
        n_init=n_init,
        normalized_stress=False,
        max_iter=300,
    )
    coords = mds.fit_transform(dist_mat)  # (n, 2)

    # ── 3. Centre on focal ───────────────────────────────────────────
    focal_idx = next((i for i, s in enumerate(songs) if s["id"] == focal_id), 0)
    coords = coords - coords[focal_idx]

    # ── 4. Scale: 75th-percentile non-focal distance → 1.0 ──────────
    non_focal_mask = np.ones(n, dtype=bool)
    non_focal_mask[focal_idx] = False
    if non_focal_mask.any():
        dists = np.linalg.norm(coords[non_focal_mask], axis=1)
        p75 = float(np.percentile(dists, 75))
        if p75 > 1e-8:
            coords = coords / p75

    # ── 5. Procrustes rotation + exact snap for overlap songs ────────────
    #
    # Two-phase approach:
    #   a) Procrustes rotation: find the 2-D rotation R (det = +1) that best
    #      maps MDS positions of overlap songs to their old positions.  Apply
    #      R to ALL points so that brand-new songs land in the correct frame.
    #   b) Snap: place every overlap song at its exact re-centred old position.
    #      The focal is always at the origin; new songs keep their (rotated)
    #      MDS positions; only songs that existed before are pinned exactly.
    if previous_positions and focal_id in previous_positions:
        fx_old, fy_old = previous_positions[focal_id]

        # Collect non-focal songs that appear in both layouts
        A_rows: list[list[float]] = []   # new MDS positions
        B_rows: list[list[float]] = []   # old positions re-centred on new focal
        overlap_entries: list[tuple[int, float, float]] = []  # (row_idx, bx, by)

        for i, song in enumerate(songs):
            sid = song["id"]
            if sid == focal_id:
                continue  # (0, 0) in both frames — contributes nothing
            if sid in previous_positions:
                px_old, py_old = previous_positions[sid]
                bx, by = px_old - fx_old, py_old - fy_old
                A_rows.append(coords[i].tolist())
                B_rows.append([bx, by])
                overlap_entries.append((i, bx, by))

        if len(A_rows) >= 1:
            A = np.array(A_rows, dtype=np.float64)
            B = np.array(B_rows, dtype=np.float64)

            # Phase a — Procrustes rotation
            # Orthogonal Procrustes: min ||A R - B||_F  s.t. R^T R = I, det R = +1
            M = A.T @ B
            U, _s, Vt = np.linalg.svd(M)
            R = U @ Vt
            if np.linalg.det(R) < 0:
                U[:, -1] *= -1
                R = U @ Vt
            coords = coords @ R  # orient new songs correctly; focal (0,0) stays

            # Phase b — snap each overlap song to its exact old position
            for idx, bx, by in overlap_entries:
                coords[idx, 0] = bx
                coords[idx, 1] = by

    return _build_points(songs, coords, dims=2)


def invalidate_cache() -> None:
    """Clear projection caches (e.g. if the song corpus changes)."""
    global _cached_all_2d, _cached_all_3d
    _cached_all_2d = None
    _cached_all_3d = None
