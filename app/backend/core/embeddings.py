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

# Small, deliberate. Genre nudges the ranking but never overrides the text
# signal — the user wants "a little" genre influence, not infinite. With
# both vectors L2-normalised, ``GENRE_WEIGHT`` is the maximum genre bonus a
# song can earn on top of its [0, 1]-normalised text score.
GENRE_WEIGHT = 0.15

# Percentile cut-offs applied to normalised scores. The query filter keeps
# only the top ~10% so the visualization actually feels selective — at 70
# (top 30%) ~1300 songs survived the first chip and the dim/highlight on
# the scatter looked indistinguishable from "everything active". Similarity
# chips stay broad on purpose — clicking a song should pull in many cousins
# so that stacking 3-4 chips intersects to a meaningful "similar to all of
# these" set instead of one or two near-duplicates.
QUERY_PERCENTILE = 90.0
SIMILAR_PERCENTILE = 50.0

# Field rows used when combining per-field cosines for song-to-song
# similarity. EMBEDDING_FIELD_COLUMNS order is
# (lyrics, description, title, album, artist) — we deliberately skip
# album (too noisy: same album → trivially similar) and use the four
# semantic fields.
#
# Combination is a self-weighted mean (sum(s^p) / sum(s^(p-1))) *gated*
# by the top field score raised to ``SIMILAR_GATE_POWER``. The gate is
# what makes a low best-field collapse the whole score, while a high
# best-field carries the song near its max:
#
#     score = (sum s_i^p / sum s_i^(p-1)) · max(s_i)^g
#
#   [0.95, 0.10, 0.10, 0.10] → 0.947 · 0.95   ≈ 0.90  (one strong field carries it)
#   [0.80, 0.80, 0.80, 0.80] → 0.800 · 0.80   ≈ 0.64  (balanced, still decent)
#   [0.60, 0.10, 0.10, 0.10] → 0.593 · 0.60   ≈ 0.36  (top field too weak → collapses)
#   [0.95, 0.95, 0.95, 0.10] → 0.950 · 0.95   ≈ 0.90
#   [0.30, 0.30, 0.30, 0.30] → 0.300 · 0.30   ≈ 0.09  (all weak → near zero)
#
# Higher ``SIMILAR_GATE_POWER`` punishes low-max candidates harder.
SIMILAR_FIELDS = (0, 1, 2, 4)  # lyrics, description, title, artist
SIMILAR_FIELD_POWER = 4.0
SIMILAR_GATE_POWER  = 0.5


# ── Fast vectorised path ────────────────────────────────────────────────────
#
# These functions consume the pre-built dense index from data_loader
# (``get_visible_index``) and avoid the per-call (n, F, D) block allocation
# that made /filter slow.  Inputs are row indices into the visible matrix;
# outputs are (idx, score) tuples ready for the route to attach metadata.


def _resolve_subset(song_ids: list[int] | None, index: dict) -> np.ndarray:
    """Map a list of song ids to row indices into the visible matrix.

    ``None`` selects every visible song. Unknown ids are silently dropped.
    """
    id_to_idx = index["id_to_idx"]
    if song_ids is None:
        return np.arange(len(id_to_idx), dtype=np.int64)
    out = [id_to_idx[i] for i in song_ids if i in id_to_idx]
    return np.asarray(out, dtype=np.int64)


def filter_embeddings_fast(
    query_text: str,
    song_ids: list[int] | None,
    index: dict,
) -> list[tuple[int, float]]:
    """Vectorised query-text filter over the dense visible index.

    Returns a list of ``(row_idx, score)`` pairs sorted by score desc.
    Always non-empty when the subset is non-empty: if everything is below
    the percentile we return the single best row.

    Scoring is the same multi-field late fusion as the legacy path
    (per-field mean centering, max over fields, min-max normalisation,
    small genre-centroid bonus), only the data path is fast: one ``(n*F)
    × D`` matmul against the row slice instead of allocating + filling a
    fresh block per call.
    """
    sub_idx = _resolve_subset(song_ids, index)
    if sub_idx.size == 0:
        return []

    matrix = index["matrix"]      # (N, F, D)
    valid  = index["valid"]       # (N, F)
    genre_matrix = index["genre_matrix"]
    genre_valid  = index["genre_valid"]
    songs = index["songs"]

    n = sub_idx.size
    F, D = matrix.shape[1], matrix.shape[2]

    if not query_text.strip() or F == 0 or D == 0:
        return [(int(i), 0.5) for i in sub_idx]

    try:
        q = np.asarray(encode_query(query_text), dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding model unavailable (%s), using text fallback.", exc)
        return _word_overlap_filter_fast(query_text, sub_idx, songs)

    q_norm = float(np.linalg.norm(q))
    if q_norm < 1e-12:
        return [(int(i), 0.5) for i in sub_idx]
    q = q / q_norm

    sub_M = matrix[sub_idx]            # (n, F, D)
    sub_V = valid[sub_idx]             # (n, F)

    # One matmul: (n*F, D) · (D,) → (n*F,) → (n, F)
    sims = (sub_M.reshape(n * F, D) @ q).reshape(n, F)
    sims = np.clip(sims, -1.0, 1.0).astype(np.float64)

    # Per-field mean across the candidate subset, masking missing fields
    # so they don't drag the mean toward 0.
    counts = sub_V.sum(axis=0).clip(min=1)
    field_mean = np.where(sub_V, sims, 0.0).sum(axis=0) / counts
    centered = sims - field_mean
    centered = np.where(sub_V, centered, -np.inf)
    raw_scores = centered.max(axis=1)

    # Min-max into [0, 1] so the percentile threshold is well calibrated.
    s_min, s_max = float(raw_scores.min()), float(raw_scores.max())
    spread = s_max - s_min
    if spread > 1e-6:
        norm_scores = (raw_scores - s_min) / spread
    else:
        norm_scores = np.full_like(raw_scores, 0.5)

    # Genre-centroid bonus: nudge toward genres dominant among text
    # leaders. Same intent as the legacy ``_apply_query_genre_bonus`` but
    # vectorised over the slice.
    if genre_matrix is not None and genre_valid is not None and n > 0:
        sub_GV = genre_valid[sub_idx]
        if sub_GV.any():
            sub_G = genre_matrix[sub_idx]
            k = min(25, n)
            leader_idx = np.argpartition(-norm_scores, k - 1)[:k]
            leader_G  = sub_G[leader_idx]
            leader_V  = sub_GV[leader_idx]
            if leader_V.any():
                centroid = leader_G[leader_V].sum(axis=0)
                c_norm = float(np.linalg.norm(centroid))
                if c_norm > 1e-9:
                    centroid = centroid / c_norm
                    bonus = np.clip(sub_G @ centroid, 0.0, 1.0)
                    bonus = np.where(sub_GV, bonus, 0.0)
                    boosted = norm_scores + GENRE_WEIGHT * bonus
                    b_min, b_max = float(boosted.min()), float(boosted.max())
                    bspread = b_max - b_min
                    if bspread > 1e-6:
                        norm_scores = (boosted - b_min) / bspread
                    else:
                        norm_scores = boosted

    threshold = float(np.percentile(norm_scores, QUERY_PERCENTILE))
    keep = norm_scores >= threshold
    if not keep.any():
        keep = np.zeros_like(keep)
        keep[int(np.argmax(norm_scores))] = True

    survivors = [
        (int(sub_idx[i]), float(round(norm_scores[i], 4)))
        for i in np.where(keep)[0]
    ]
    survivors.sort(key=lambda t: t[1], reverse=True)
    return survivors


def filter_by_similarity_fast(
    focal_id: int,
    song_ids: list[int] | None,
    index: dict,
    percentile: float = SIMILAR_PERCENTILE,
) -> list[tuple[int, float]]:
    """Vectorised song-to-song similarity filter over the dense visible index.

    Acts as a *filter*, not a top-k: returns every song whose similarity to
    the focal is above ``percentile`` of the normalised score, so the
    chip behaves like the query chip and stacking multiple chips composes
    naturally into "similar to all of these".

    Scoring combines per-field cosines (title, lyrics, artist, description)
    via a self-weighted mean — a single very strong field carries the
    score, while balanced low scores collapse. See ``SIMILAR_FIELDS`` and
    ``SIMILAR_FIELD_POWER`` for the formula.
    """
    id_to_idx = index["id_to_idx"]
    focal_idx_full = id_to_idx.get(int(focal_id))
    if focal_idx_full is None:
        return []

    matrix = index["matrix"]   # (N, F, D)
    valid  = index["valid"]    # (N, F)
    if matrix.shape[1] == 0 or matrix.shape[2] == 0:
        return []

    sub_idx = _resolve_subset(song_ids, index)
    if sub_idx.size == 0:
        sub_idx = np.array([focal_idx_full], dtype=np.int64)
    if focal_idx_full not in sub_idx:
        sub_idx = np.append(sub_idx, focal_idx_full)

    # Restrict to fields that actually exist in the matrix; preserves the
    # configured order so weighting stays predictable.
    F_total = matrix.shape[1]
    use_fields = [f for f in SIMILAR_FIELDS if f < F_total]
    if not use_fields:
        return []

    focal_block = matrix[focal_idx_full, use_fields, :]      # (Fu, D)
    focal_valid = valid[focal_idx_full, use_fields]          # (Fu,)
    if not focal_valid.any():
        return []

    sub_block = matrix[sub_idx][:, use_fields, :]            # (n, Fu, D)
    sub_valid = valid[sub_idx][:, use_fields]                # (n, Fu)

    # Per-field cosine: candidate.field · focal.field, done in one
    # einsum so each candidate's field aligns with the focal's matching
    # field (title↔title, lyrics↔lyrics, …).
    per_field = np.einsum("nfd,fd->nf", sub_block, focal_block)
    per_field = np.clip(per_field, -1.0, 1.0).astype(np.float64)

    # Only fields valid on *both* sides count. Missing fields contribute
    # nothing (no weight, no signal) so they neither inflate nor deflate
    # the combined score.
    field_mask = sub_valid & focal_valid[None, :]
    # Map cosines into [0, 1] (negative correlations don't make a song
    # "more similar"), then apply the self-weighted mean. Power p
    # determines how much the top field dominates the mean; the gate
    # below punishes candidates whose best field isn't actually strong.
    sims_pos = np.clip(per_field, 0.0, 1.0)
    sims_pos = np.where(field_mask, sims_pos, 0.0)
    p = SIMILAR_FIELD_POWER
    weights = sims_pos ** (p - 1.0)
    num = (sims_pos ** p).sum(axis=1)
    den = weights.sum(axis=1)
    self_weighted = np.where(
        den > 1e-12,
        num / np.where(den > 1e-12, den, 1.0),
        0.0,
    )

    # Gate: multiply by the candidate's best valid field, raised to g.
    # Without this gate, a single 0.60 field looks ~as relevant as a
    # single 0.95 field — both pull the self-weighted mean toward
    # themselves. The gate makes "is the best field actually strong?"
    # part of the score, so [0.60, 0.10, 0.10, 0.10] collapses far below
    # [0.95, 0.10, 0.10, 0.10] instead of sitting just below it.
    field_top = np.where(field_mask, sims_pos, 0.0).max(axis=1)
    raw = self_weighted * (field_top ** SIMILAR_GATE_POWER)

    # Small genre alignment bonus on top — same intent as before, kept
    # bounded by ``GENRE_WEIGHT`` so it nudges without overriding the
    # field signal.
    genre_matrix = index["genre_matrix"]
    genre_valid  = index["genre_valid"]
    if genre_matrix is not None and genre_valid is not None and genre_valid[focal_idx_full]:
        focal_g = genre_matrix[focal_idx_full]
        sub_G   = genre_matrix[sub_idx]
        sub_GV  = genre_valid[sub_idx]
        bonus = np.clip(sub_G @ focal_g, 0.0, 1.0)
        bonus = np.where(sub_GV, bonus, 0.0)
        raw = raw + GENRE_WEIGHT * bonus

    # Pin focal at the top so it always survives the threshold.
    focal_pos = int(np.where(sub_idx == focal_idx_full)[0][0])
    raw[focal_pos] = float(raw.max()) + GENRE_WEIGHT + 1.0

    r_min, r_max = float(raw.min()), float(raw.max())
    spread = r_max - r_min
    if spread > 1e-6:
        norm_scores = (raw - r_min) / spread
    else:
        norm_scores = np.full_like(raw, 0.5)

    threshold = float(np.percentile(norm_scores, percentile))
    keep = norm_scores >= threshold
    keep[focal_pos] = True
    if keep.sum() < 2:
        # Force at least one neighbour besides the focal.
        order = np.argsort(-norm_scores)
        for j in order:
            if int(j) == focal_pos:
                continue
            keep[int(j)] = True
            break

    survivors = [
        (int(sub_idx[i]), float(round(norm_scores[i], 4)))
        for i in np.where(keep)[0]
    ]
    survivors.sort(key=lambda t: t[1], reverse=True)
    return survivors


def compute_cercador_suggestions(
    query_text: str,
    index: dict,
    exclude_ids: set[int] | None = None,
    suggestions_k: int = 4,
    lyrics_extra_k: int = 2,
    qualitative_field_idx: int = 1,
) -> dict:
    """Embedding-based "Sugerències" + extra lyrics for the cercador.

    One query encoding is reused for both passes:

    * **suggestions** — top ``suggestions_k`` songs ranked by raw cosine
      against the qualitative-description field (row 1 of the dense
      index). The intent is "the user described a vibe; surface songs
      whose qualitative blurb matches that vibe", so we deliberately do
      NOT max over fields here — title/artist matches are already covered
      by the keyword cercador.
    * **lyrics_extra** — top ``lyrics_extra_k`` songs ranked by
      max-over-fields cosine, with ``exclude_ids`` masked out. These
      get appended to the keyword-cercador's lyrics column so the user
      sees embedding-discovered matches the keyword index missed.

    Returns ``(row_idx, raw_cosine)`` pairs in ``suggestions`` /
    ``lyrics_extra`` keys; row indices point into ``index["songs"]``.
    Empty lists on encoder failure or empty matrix.
    """
    matrix = index["matrix"]   # (N, F, D), L2-normalised
    valid  = index["valid"]    # (N, F)
    if matrix.size == 0:
        return {"suggestions": [], "lyrics_extra": []}

    N, F, D = matrix.shape
    if F == 0 or D == 0:
        return {"suggestions": [], "lyrics_extra": []}

    try:
        q = np.asarray(encode_query(query_text), dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Suggestions: encoder unavailable (%s)", exc)
        return {"suggestions": [], "lyrics_extra": []}

    q_norm = float(np.linalg.norm(q))
    if q_norm < 1e-12:
        return {"suggestions": [], "lyrics_extra": []}
    q = q / q_norm

    # ── Suggestions: cosine vs qualitative-description field only ────
    suggestions: list[tuple[int, float]] = []
    if 0 <= qualitative_field_idx < F:
        qual_vecs = matrix[:, qualitative_field_idx, :]   # (N, D)
        qual_valid = valid[:, qualitative_field_idx]       # (N,)
        qual_sims = qual_vecs @ q                          # (N,)
        masked = np.where(qual_valid, qual_sims, -np.inf)

        valid_n = int(qual_valid.sum())
        k = min(suggestions_k, valid_n)
        if k > 0:
            top = np.argpartition(-masked, k - 1)[:k]
            top = top[np.argsort(-masked[top])]
            suggestions = [
                (int(i), float(masked[i]))
                for i in top
                if np.isfinite(masked[i])
            ]

    # ── Lyrics extra: max over fields, exclude_ids masked out ────────
    # One stacked matmul against the full (N, F, D) cube. Mask invalid
    # field cells with -inf so they can't win the max; mask excluded ids
    # with -inf so they're dropped from the top-K.
    field_sims = (matrix.reshape(N * F, D) @ q).reshape(N, F)
    field_sims = np.where(valid, field_sims, -np.inf)
    max_sims = field_sims.max(axis=1)                       # (N,)

    if exclude_ids:
        id_to_idx = index["id_to_idx"]
        excluded_pos = [id_to_idx[i] for i in exclude_ids if i in id_to_idx]
        if excluded_pos:
            max_sims[excluded_pos] = -np.inf

    lyrics_extra: list[tuple[int, float]] = []
    finite_n = int(np.isfinite(max_sims).sum())
    k2 = min(lyrics_extra_k, finite_n)
    if k2 > 0:
        top2 = np.argpartition(-max_sims, k2 - 1)[:k2]
        top2 = top2[np.argsort(-max_sims[top2])]
        lyrics_extra = [
            (int(i), float(max_sims[i]))
            for i in top2
            if np.isfinite(max_sims[i])
        ]

    return {"suggestions": suggestions, "lyrics_extra": lyrics_extra}


def _word_overlap_filter_fast(
    query_text: str,
    sub_idx: np.ndarray,
    songs: list[dict],
) -> list[tuple[int, float]]:
    """Word-overlap fallback for when the encoder is unavailable.

    Returns ``(row_idx, score)`` pairs aligned with ``sub_idx``, sorted
    desc. Always keeps at least the best-scoring row.
    """
    words = set(query_text.lower().split())
    scored: list[tuple[int, float]] = []
    for i in sub_idx:
        s = songs[int(i)]
        searchable = " ".join([
            s.get("title", ""), s.get("artist", ""),
            s.get("lyrics_snippet", ""), s.get("album", ""), s.get("genre", ""),
        ]).lower().split()
        overlap = len(words & set(searchable)) / max(len(words), 1)
        scored.append((int(i), round(0.1 + overlap * 0.8, 4)))

    if not scored:
        return []
    threshold = float(np.median([sc for _, sc in scored]))
    survivors = [(i, sc) for (i, sc) in scored if sc >= threshold]
    if not survivors:
        survivors = [max(scored, key=lambda t: t[1])]
    survivors.sort(key=lambda t: t[1], reverse=True)
    return survivors


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


def _apply_query_genre_bonus(
    norm_scores: np.ndarray,
    songs: list[dict],
    top_k: int = 25,
) -> np.ndarray:
    """Nudge ``norm_scores`` toward songs whose genre matches the top-K leaders.

    Without query-side genre labels we can't compute the user's intended
    genre directly. Instead we treat the centroid of the top-K leaders'
    genre profiles as a proxy for "what genre is this query talking about",
    then add ``GENRE_WEIGHT × cosine(centroid, song_profile)`` to each row.
    Effect: when text similarity already crowns a coherent set of, say,
    punk songs, other punk songs in the candidate set get a small boost —
    pulling the result toward genre-consistent clusters without overriding
    the text signal.

    Returns the input unchanged if no song has a profile or the top-K is
    too small / incoherent to be informative.
    """
    profiles = [s.get("genre_profile") for s in songs]
    if not any(p is not None for p in profiles):
        return norm_scores

    n = len(songs)
    if n == 0:
        return norm_scores
    k = min(top_k, n)
    leader_idx = np.argpartition(-norm_scores, k - 1)[:k]
    G = next((p.shape[0] for p in profiles if p is not None), 0)
    if G == 0:
        return norm_scores
    centroid = np.zeros(G, dtype=np.float64)
    count = 0
    for i in leader_idx:
        p = profiles[int(i)]
        if p is None or p.size != G:
            continue
        centroid += p.astype(np.float64)
        count += 1
    if count == 0:
        return norm_scores
    centroid /= count
    c_norm = float(np.linalg.norm(centroid))
    if c_norm < 1e-9:
        return norm_scores
    centroid /= c_norm

    bonus = np.zeros(n, dtype=np.float64)
    for i, p in enumerate(profiles):
        if p is None or p.size != G:
            continue
        pv = p.astype(np.float64)
        norm = float(np.linalg.norm(pv))
        if norm < 1e-9:
            continue
        bonus[i] = max(0.0, float(np.dot(centroid, pv / norm)))

    out = norm_scores + GENRE_WEIGHT * bonus
    # Re-normalise back to [0, 1] so the percentile threshold downstream
    # keeps its calibration.
    o_min, o_max = float(out.min()), float(out.max())
    spread = o_max - o_min
    if spread > 1e-6:
        return (out - o_min) / spread
    return out


def _genre_bonus(focal_profile: np.ndarray | None, songs: list[dict]) -> np.ndarray:
    """Per-song genre-alignment bonus in [0, 1] aligned with ``songs``.

    Returns zeros if either the focal profile or every song profile is
    missing. The bonus is the L2-cosine between profiles, clipped to [0, 1]
    (negative correlation is collapsed to zero so it can only help, never
    actively hurt). Callers scale this by ``GENRE_WEIGHT``.
    """
    n = len(songs)
    if focal_profile is None or focal_profile.size == 0:
        return np.zeros(n, dtype=np.float64)

    profiles = [s.get("genre_profile") for s in songs]
    if not any(p is not None for p in profiles):
        return np.zeros(n, dtype=np.float64)

    f = focal_profile.astype(np.float64)
    f_norm = float(np.linalg.norm(f))
    if f_norm < 1e-9:
        return np.zeros(n, dtype=np.float64)
    f = f / f_norm

    G = focal_profile.shape[0]
    out = np.zeros(n, dtype=np.float64)
    for i, p in enumerate(profiles):
        if p is None or p.size != G:
            continue
        pv = p.astype(np.float64)
        norm = float(np.linalg.norm(pv))
        if norm < 1e-9:
            continue
        out[i] = max(0.0, float(np.dot(f, pv / norm)))
    return out


def filter_embeddings(query_text: str, songs: list[dict]) -> list[dict]:
    """
    Progressive semantic filter with multi-field late fusion.

    Given a query and the CURRENT subset of songs (already narrowed by
    previous queries), returns a further-filtered subset with relevance scores.

    Algorithm
    ---------
    1. Encode query_text with encoder.encode_query() → MODEL_DIM bge-m3 vector.
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

    # ── Small genre-alignment bonus ──────────────────────────────────────
    # We don't have the query's genre label embeddings handy, so we derive
    # the query's implied genre profile from the top-scoring songs (centroid
    # of their genre profiles) and reward songs whose own profile aligns.
    # The query-classification problem is bypassed: similar songs to those
    # already winning on text get a nudge, similar to clustering snap-back.
    norm_scores = _apply_query_genre_bonus(norm_scores, songs)

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

    Why centering: different fields have different intrinsic similarity
    baselines against an arbitrary query (short fields like title/artist
    cluster differently from long fields like lyrics). Without centering,
    whichever field has the higher baseline tends to win the ``max`` and
    the user query barely affects ranking.

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


def filter_by_similarity(
    focal_id: int,
    songs: list[dict],
    percentile: float = 70.0,
) -> list[dict]:
    """Song-to-song similarity filter used by the "search similar" chip.

    Combines L2 cosine over lyrics with a small genre-profile alignment
    bonus (controlled by ``GENRE_WEIGHT``), then keeps songs above
    ``percentile`` of the normalised score. Always returns the focal song
    plus at least one other survivor.
    """
    if not songs:
        return []
    focal_idx = next((i for i, s in enumerate(songs) if s["id"] == focal_id), None)
    if focal_idx is None:
        return []

    try:
        matrix = np.array([s["embedding"] for s in songs], dtype=np.float64)
    except (TypeError, ValueError):
        return []
    if matrix.size == 0 or matrix.shape[1] == 0:
        return []

    sims = cosine_vector(matrix[focal_idx], matrix)
    bonus = _genre_bonus(songs[focal_idx].get("genre_profile"), songs)
    raw = sims + GENRE_WEIGHT * bonus
    raw[focal_idx] = 1.0 + GENRE_WEIGHT  # guarantee focal stays on top

    s_min, s_max = float(raw.min()), float(raw.max())
    spread = s_max - s_min
    if spread > 1e-6:
        norm_scores = (raw - s_min) / spread
    else:
        norm_scores = np.full_like(raw, 0.5)

    threshold = float(np.percentile(norm_scores, percentile))
    survivors: list[dict] = []
    for i, song in enumerate(songs):
        if i == focal_idx or norm_scores[i] >= threshold:
            survivors.append({**song, "score": round(float(norm_scores[i]), 4)})

    if len(survivors) < 2:
        order = np.argsort(-norm_scores)
        for i in order:
            if int(i) == focal_idx:
                continue
            survivors.append({**songs[int(i)], "score": round(float(norm_scores[int(i)]), 4)})
            break

    survivors.sort(key=lambda s: s["score"], reverse=True)
    return survivors


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
    bonus = _genre_bonus(focal_song.get("genre_profile"), songs)
    combined = sims + GENRE_WEIGHT * bonus

    scored = [
        {**song, "score": round(float(combined[i]), 4)}
        for i, song in enumerate(songs)
        if i != focal_idx
    ]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return [{**focal_song, "score": 1.0}] + scored[:n]
