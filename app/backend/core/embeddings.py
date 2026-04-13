"""
Embedding and similarity module — progressive filtering.

Encodes queries via core/encoder.py (which is the single place to edit when
switching models or passage formats).  Songs must already carry an 'embedding'
field whose dimension matches encoder.MODEL_DIM.

If the song embeddings are a different dimension (e.g. the 32-dim mock data),
filter_embeddings falls back to a word-overlap scorer so the dev environment
still works before real embeddings are generated.
"""

from __future__ import annotations

import logging

import numpy as np

from app.backend.core.encoder import encode_query

logger = logging.getLogger(__name__)


def compute_similarity(query_embedding: list[float], song_embedding: list[float]) -> float:
    """
    Cosine similarity between two embedding vectors.

    Both vectors are L2-normalised before the dot product so the result is
    in [-1, 1].  Returns 0.0 if either vector is the zero vector.
    """
    q = np.array(query_embedding, dtype=np.float64)
    s = np.array(song_embedding, dtype=np.float64)
    q_norm = np.linalg.norm(q)
    s_norm = np.linalg.norm(s)
    if q_norm == 0.0 or s_norm == 0.0:
        return 0.0
    return float(np.dot(q, s) / (q_norm * s_norm))


def filter_embeddings(query_text: str, songs: list[dict]) -> list[dict]:
    """
    Progressive semantic filter.

    Given a query and the CURRENT subset of songs (already narrowed by
    previous queries), returns a further-filtered subset with relevance scores.

    Algorithm
    ---------
    1. Encode query_text with encoder.encode_query() → MODEL_DIM e5 vector.
    2. Compute cosine similarity between the query and every song's embedding.
    3. Threshold = median score of the current set.  Songs at or above the
       median survive; this keeps roughly the top half, so repeated queries
       progressively narrow the set.
    4. Never return an empty list — if everything is cut, return the single
       best-scoring song.

    Fallback (dimension mismatch)
    -----------------------------
    When the song embedding dimension does not match the model output (e.g.
    the 32-dim mock data), falls back to word-overlap scoring so the dev
    environment still works before real embeddings are generated.

    Args:
        query_text: The user's search query.
        songs:      Current surviving songs (each must have an 'embedding' field).
    Returns:
        Filtered list with an added 'score' field, sorted descending.
        Always contains ≥ 1 song.
    """
    if not songs:
        return []

    if not query_text.strip():
        return [{**s, "score": 0.5} for s in songs]

    # ── Encode query ──────────────────────────────────────────────────
    try:
        query_emb = np.array(encode_query(query_text), dtype=np.float64)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding model unavailable (%s), using text fallback.", exc)
        return _word_overlap_filter(query_text, songs)

    q_norm = np.linalg.norm(query_emb)
    if q_norm == 0.0:
        return [{**s, "score": 0.5} for s in songs]

    # ── Dimension check ───────────────────────────────────────────────
    song_dim = len(songs[0].get("embedding") or [])
    if song_dim != len(query_emb):
        logger.warning(
            "Song embedding dim (%d) ≠ query embedding dim (%d). "
            "Using text fallback — regenerate embeddings with preembedding.py.",
            song_dim, len(query_emb),
        )
        return _word_overlap_filter(query_text, songs)

    # ── Cosine similarity for every song ─────────────────────────────
    song_matrix = np.array([s["embedding"] for s in songs], dtype=np.float64)
    norms = np.linalg.norm(song_matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    song_matrix_normed = song_matrix / norms

    query_normed = query_emb / q_norm
    raw_scores = song_matrix_normed @ query_normed  # (n,) in [-1, 1]

    # ── Min-max normalise so scores use the full [0, 1] range ────────
    # Embedding scores for similar-domain content (e.g. all Catalan pop songs)
    # are tightly clustered (range ~0.06).  Without normalisation the median
    # threshold is nearly meaningless — top and bottom songs differ by <0.01.
    s_min, s_max = float(raw_scores.min()), float(raw_scores.max())
    spread = s_max - s_min
    if spread > 1e-6:
        norm_scores = (raw_scores - s_min) / spread   # → [0, 1]
    else:
        norm_scores = np.full_like(raw_scores, 0.5)

    # ── Threshold: keep top 30 % (70th percentile of normalised scores) ──
    # Tighter than the old median (50 %) so each query is more selective.
    threshold = float(np.percentile(norm_scores, 70))
    scored = [
        {**song, "score": round(float(norm_scores[i]), 4)}
        for i, song in enumerate(songs)
    ]
    survivors = [s for s in scored if s["score"] >= threshold]

    if not survivors:
        survivors = [max(scored, key=lambda s: s["score"])]

    survivors.sort(key=lambda s: s["score"], reverse=True)
    return survivors


# ── Fallback ──────────────────────────────────────────────────────────────────

def _word_overlap_filter(query_text: str, songs: list[dict]) -> list[dict]:
    """
    Word-overlap scorer used when embedding dimensions don't match.

    Scores each song by the fraction of query words found in its text fields.
    Applies the same median threshold as the real filter.
    """
    words = set(query_text.lower().split())
    scored = []
    for song in songs:
        searchable = " ".join([
            song.get("title", ""),
            song.get("artist", ""),
            song.get("lyrics_snippet", ""),
            song.get("album", ""),
            song.get("genre", ""),
        ]).lower().split()
        searchable_set = set(searchable)
        overlap = len(words & searchable_set) / max(len(words), 1)
        # Map to [0.1, 0.9] so the range is meaningful
        score = round(0.1 + overlap * 0.8, 4)
        scored.append({**song, "score": score})

    threshold = float(np.median([s["score"] for s in scored]))
    survivors = [s for s in scored if s["score"] >= threshold]
    if not survivors:
        survivors = [max(scored, key=lambda s: s["score"])]

    return sorted(survivors, key=lambda s: s["score"], reverse=True)


def build_neighborhood(
    focal_id: int,
    all_songs: list[dict],
    n: int = 20,
    previous_song_id: int | None = None,
    bridge_song_ids: list[int] | None = None,
    bridge_count: int = 5,
) -> list[dict]:
    """
    Build the full neighborhood set for graph-style exploration.

    Assigns a 'role' field to each song:
      "focal"    — the song being explored (always first)
      "neighbor" — one of the N nearest neighbors by cosine similarity
      "previous" — the song from which the user navigated here (always included)
      "bridge"   — added from the previous neighborhood for visual continuity

    Args:
        focal_id:        ID of the song being explored.
        all_songs:       Full song catalog (each must have 'embedding').
        n:               Number of nearest neighbors to include.
        previous_song_id: Song explored in the previous step.
        bridge_song_ids: IDs of songs in the previous neighborhood.
        bridge_count:    How many bridge songs to add (chosen by similarity to focal).

    Returns:
        Combined list with 'role' and 'score' fields added.
    """
    id_to_song = {s["id"]: s for s in all_songs}

    # ── Core neighborhood ────────────────────────────────────────────
    base = get_nearest_neighbors(focal_id, all_songs, n=n)
    neighborhood_ids: set[int] = {s["id"] for s in base}

    result: list[dict] = []
    for song in base:
        role = "focal" if song["id"] == focal_id else "neighbor"
        result.append({**song, "role": role})

    # ── Previous focal ───────────────────────────────────────────────
    if previous_song_id is not None:
        if previous_song_id not in neighborhood_ids:
            prev = id_to_song.get(previous_song_id)
            if prev:
                result.append({**prev, "score": 0.0, "role": "previous"})
                neighborhood_ids.add(previous_song_id)
        else:
            # Already a natural neighbor — elevate its role
            for s in result:
                if s["id"] == previous_song_id:
                    s["role"] = "previous"
                    break

    # ── Bridge songs ─────────────────────────────────────────────────
    if bridge_song_ids and bridge_count > 0:
        focal_song_data = id_to_song.get(focal_id)
        if focal_song_data:
            focal_emb = np.array(focal_song_data["embedding"], dtype=np.float64)
            focal_norm = np.linalg.norm(focal_emb) or 1.0

            candidates: list[tuple[float, dict]] = []
            for bid in bridge_song_ids:
                if bid in neighborhood_ids:
                    continue
                b_song = id_to_song.get(bid)
                if not b_song:
                    continue
                emb = np.array(b_song["embedding"], dtype=np.float64)
                norm = np.linalg.norm(emb)
                sim = float(np.dot(focal_emb, emb) / (focal_norm * norm)) if norm > 0 else 0.0
                candidates.append((sim, b_song))

            candidates.sort(key=lambda x: x[0], reverse=True)
            for _, b_song in candidates[:bridge_count]:
                result.append({**b_song, "score": 0.0, "role": "bridge"})
                neighborhood_ids.add(b_song["id"])

    return result


def get_nearest_neighbors(focal_id: int, songs: list[dict], n: int = 20) -> list[dict]:
    """
    Find the N nearest songs to focal_id by cosine similarity of embeddings.

    The focal song itself is included first with score 1.0, followed by the
    N most similar songs sorted by similarity descending.

    Args:
        focal_id: ID of the focal song.
        songs:    Full song catalog (each must have 'embedding').
        n:        Number of neighbors to return (excluding the focal song).

    Returns:
        List of song dicts with an added 'score' field (cosine similarity).
        Always contains at least the focal song if it exists.
    """
    focal_song = next((s for s in songs if s["id"] == focal_id), None)
    if focal_song is None:
        return []

    focal_emb = np.array(focal_song["embedding"], dtype=np.float64)
    focal_norm = np.linalg.norm(focal_emb)
    if focal_norm == 0:
        focal_norm = 1.0

    scored: list[dict] = []
    for song in songs:
        if song["id"] == focal_id:
            continue
        emb = np.array(song["embedding"], dtype=np.float64)
        norm = np.linalg.norm(emb)
        sim = float(np.dot(focal_emb, emb) / (focal_norm * norm)) if norm > 0 else 0.0
        scored.append({**song, "score": round(sim, 4)})

    scored.sort(key=lambda s: s["score"], reverse=True)
    return [{**focal_song, "score": 1.0}] + scored[:n]
