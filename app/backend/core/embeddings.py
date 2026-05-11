"""
Embedding and similarity module — progressive filtering.

Encodes queries via core/encoder.py (the single place to edit when switching
models or passage formats).

Query scoring is **multi-field late fusion**: each song carries an
``embedding_fields`` matrix (one row per field — lyrics, qualitative
description, title, album, artist) and the per-song score is the max cosine
similarity across those rows.  Effect: a query that names an artist lights
up the artist row; a query that quotes a chorus lights up the lyrics row;
the user doesn't have to know which.

Song-to-song similarity (``get_nearest_neighbors`` / ``build_neighborhood``)
continues to use the lyrics vector only — for "show me similar songs" the
lyrical content is what's actually meant, and using max-over-fields there
would let two unrelated songs by the same artist look like duplicates.

If a dimension mismatch is detected (e.g. an outdated parquet was loaded
against a newer encoder), filter_embeddings falls back to a word-overlap
scorer so the API stays responsive while you regenerate embeddings.
"""

from __future__ import annotations

import logging

import numpy as np

from app.backend.core.encoder import encode_query
from app.backend.core.similarity import (
    cosine_vector,
    l2_normalize_matrix,
    l2_normalize_vector,
)

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
    Progressive semantic filter with multi-field late fusion.

    Given a query and the CURRENT subset of songs (already narrowed by
    previous queries), returns a further-filtered subset with relevance scores.

    Algorithm
    ---------
    1. Encode query_text with encoder.encode_query() → MODEL_DIM e5 vector.
    2. For each song, compute cosine similarity against every field embedding
       (lyrics, qualitative description, title, album, artist) and take the
       maximum.  This is late fusion: each query type naturally picks the
       field that matches it best.
    3. Min-max-normalise scores so the (typically narrow) cosine spread fills
       the [0, 1] range, then keep songs above the 70th percentile.
    4. Never return an empty list — if everything is cut, return the single
       best-scoring song.

    Fallback (dimension mismatch / missing fields)
    ----------------------------------------------
    If neither ``embedding_fields`` nor ``embedding`` is usable at the
    expected dim, falls back to word-overlap scoring.

    Args:
        query_text: The user's search query.
        songs:      Current surviving songs.  Each should have either an
                    ``embedding_fields`` ndarray (preferred) or an
                    ``embedding`` list (single-vector legacy path).
    Returns:
        Filtered list with an added ``score`` field, sorted descending.
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

    # ── Score every song: max cosine over fields ─────────────────────
    raw_scores = _score_songs_multifield(query_emb, songs)
    if raw_scores is None:
        # Multi-field path unavailable for these songs (dim mismatch or no
        # fields attached). Fall back to single-vector / word overlap.
        song_dim = len(songs[0].get("embedding") or [])
        if song_dim != len(query_emb):
            logger.warning(
                "Song embedding dim (%d) ≠ query embedding dim (%d). "
                "Using text fallback — regenerate embeddings with preembedding.py.",
                song_dim, len(query_emb),
            )
            return _word_overlap_filter(query_text, songs)
        song_matrix = np.array([s["embedding"] for s in songs], dtype=np.float64)
        raw_scores = cosine_vector(query_emb, song_matrix)

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


# ── Multi-field late fusion ──────────────────────────────────────────────────

def _score_songs_multifield(
    query_emb: np.ndarray,
    songs: list[dict],
) -> np.ndarray | None:
    """
    Per-song score = max over fields of *centered* cosine similarity to query.

    Why centering: ``preembedding.py`` produced title / album / artist
    embeddings with the ``"query: "`` prefix while lyrics and qualitative-
    description use ``"passage: "``. E5 is asymmetric and query-vs-query
    cosines have a systematically higher baseline (~+0.10) than query-vs-
    passage, regardless of content match. Without centering, the title-space
    fields always win ``max`` and the user query barely affects ranking.

    The fix is per-query per-field mean subtraction: for each field we compute
    the mean cosine across the candidate set and subtract it before taking the
    max. What survives is "how unusually aligned with the query is this song
    in field F, relative to a typical song in field F" — the quantity late
    fusion is supposed to be measuring.

    Returns ``None`` if the multi-field path can't be used (no fields
    attached, or dim mismatch). On success returns an ``(n,)`` float64 vector
    aligned with ``songs``.

    Implementation: one stacked matmul into ``(n, F)`` cosines, vectorised
    centering, vectorised max. ~1 ms for n=5000 on CPU.
    """
    matrices = [s.get("embedding_fields") for s in songs]
    if not any(m is not None for m in matrices):
        return None

    expected_dim = len(query_emb)
    n = len(songs)
    F = max((m.shape[0] for m in matrices if m is not None), default=0)
    if F == 0:
        return None

    # ``valid_mask[i, f]`` flags real (non-zero) field embeddings; zeros are
    # missing data and must NOT contribute to the per-field mean.
    block = np.zeros((n, F, expected_dim), dtype=np.float64)
    valid_mask = np.zeros((n, F), dtype=bool)
    for i, m in enumerate(matrices):
        if m is None or m.size == 0:
            continue
        if m.shape[1] != expected_dim:
            logger.warning(
                "Song embedding dim (%d) ≠ query dim (%d); dropping that row.",
                m.shape[1], expected_dim,
            )
            continue
        f = min(m.shape[0], F)
        block[i, :f, :] = m[:f]
        valid_mask[i, :f] = True
    if not valid_mask.any():
        return None

    q = query_emb / max(float(np.linalg.norm(query_emb)), 1e-12)
    sims = np.clip(block.reshape(n * F, expected_dim) @ q, -1.0, 1.0).reshape(n, F)

    # Per-field mean across the *candidate* set (mask out missing fields so
    # they don't drag the mean toward 0).
    counts = valid_mask.sum(axis=0).clip(min=1)            # (F,)
    field_mean = (sims * valid_mask).sum(axis=0) / counts  # (F,)
    centered = sims - field_mean                            # (n, F)

    # A missing field shouldn't be eligible to win the max; replace its
    # centered value with -inf so it can never beat a real field.
    centered = np.where(valid_mask, centered, -np.inf)
    return centered.max(axis=1)


# ── Fallback ──────────────────────────────────────────────────────────────────

def _word_overlap_filter(query_text: str, songs: list[dict]) -> list[dict]:
    """
    Word-overlap scorer used when embedding dimensions don't match.

    Scores each song by the fraction of query words found in its text
    fields, then keeps every song with score ≥ median. Always returns at
    least one survivor (the highest-scoring song).
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
            bridge_pool: list[dict] = []
            for bid in bridge_song_ids:
                if bid in neighborhood_ids:
                    continue
                b_song = id_to_song.get(bid)
                if b_song is not None:
                    bridge_pool.append(b_song)

            if bridge_pool:
                focal_emb = np.array(focal_song_data["embedding"], dtype=np.float64)
                bridge_matrix = np.array(
                    [b["embedding"] for b in bridge_pool], dtype=np.float64
                )
                sims = cosine_vector(focal_emb, bridge_matrix)
                order = np.argsort(-sims)[:bridge_count]
                for idx in order:
                    b_song = bridge_pool[int(idx)]
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
    focal_idx = next((i for i, s in enumerate(songs) if s["id"] == focal_id), None)
    if focal_idx is None:
        return []
    focal_song = songs[focal_idx]

    matrix = np.array([s["embedding"] for s in songs], dtype=np.float64)
    sims = cosine_vector(matrix[focal_idx], matrix)

    scored = [
        {**song, "score": round(float(sims[i]), 4)}
        for i, song in enumerate(songs)
        if i != focal_idx
    ]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return [{**focal_song, "score": 1.0}] + scored[:n]
