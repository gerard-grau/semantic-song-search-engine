"""
Embedding and similarity module — progressive filtering.

Encodes queries via core/encoder.py (the single place to edit when switching
models or passage formats).

Query scoring is **multi-field late fusion**: each song carries an
``embedding_fields`` matrix (one row per field — lyrics, qualitative
description, title, album, artist) and the per-song score is the max cosine
similarity across those rows. Effect: a query that names an artist lights
up the artist row; a query that quotes a chorus lights up the lyrics row;
the user doesn't have to know which.

Song-to-song similarity (``get_nearest_neighbors`` / ``build_neighborhood``)
uses the lyrics vector only — for "show me similar songs" the lyrical
content is what's actually meant, and using max-over-fields there would
let two unrelated songs by the same artist look like duplicates.

If the embedding model is unavailable, ``filter_embeddings_fast`` falls
back to a word-overlap scorer so the API stays responsive.
"""

from __future__ import annotations

import logging

import numpy as np

import config
from app.backend.core.encoder import encode_query
from app.backend.core.similarity import cosine_vector

logger = logging.getLogger(__name__)

# All tuning constants come from config.py — see that file for rationale.
# Re-bound at module level so existing callers (and tests) can keep using
# ``from app.backend.core.embeddings import GENRE_WEIGHT`` etc.
GENRE_WEIGHT                  = config.GENRE_WEIGHT
QUERY_DISCRIM_REF             = config.QUERY_DISCRIM_REF
QUERY_DISCRIM_FLOOR           = config.QUERY_DISCRIM_FLOOR
SIMILAR_PERCENTILE            = config.SIMILAR_PERCENTILE
SIMILAR_FIELDS                = config.SIMILAR_FIELDS
SIMILAR_FIELD_POWER           = config.SIMILAR_FIELD_POWER
SIMILAR_GATE_POWER            = config.SIMILAR_GATE_POWER
SUGGESTION_FIELDS             = config.SUGGESTION_FIELDS
SUGGESTION_COSINE_FLOOR       = config.SUGGESTION_COSINE_FLOOR
ARTIST_FIELD_IDX              = config.ARTIST_FIELD_IDX
GROUP_SUGGESTION_COSINE_FLOOR = config.GROUP_SUGGESTION_COSINE_FLOOR


# ── Fast vectorised path ────────────────────────────────────────────────────
#
# These functions consume the pre-built dense index from data_loader
# (``get_visible_index``) and avoid the per-call (n, F, D) block allocation
# that made /filter slow.  Inputs are row indices into the visible matrix;
# outputs are (idx, score) tuples ready for the route to attach metadata.


def filter_embeddings_fast(
    query_text: str,
    song_ids: list[int] | None,
    index: dict,
) -> list[tuple[int, float]]:
    """Vectorised query-text filter over the dense visible index.

    Returns a list of ``(row_idx, score)`` pairs sorted by score desc.

    Scoring and thresholding are **computed over the entire visible
    catalog**, never over ``song_ids``. ``song_ids`` is only used at the
    end to intersect global survivors with the caller-supplied alive set
    — that makes chip composition commutative (``[A, B]`` and ``[B, A]``
    return the same survivors and the same per-song score), and removes
    the echo-chamber feedback that biased the genre centroid toward
    artists already over-represented in the subset.
    """
    matrix = index["matrix"]      # (N, F, D)
    valid  = index["valid"]       # (N, F)
    genre_matrix = index["genre_matrix"]
    genre_valid  = index["genre_valid"]
    songs = index["songs"]
    id_to_idx = index["id_to_idx"]

    N, F, D = matrix.shape

    # Subset to intersect at the end. ``None`` → keep every visible song.
    if song_ids is None:
        sub_idx = np.arange(N, dtype=np.int64)
    else:
        sub_idx = np.asarray(
            [id_to_idx[i] for i in song_ids if i in id_to_idx],
            dtype=np.int64,
        )
    if sub_idx.size == 0:
        return []

    if not query_text.strip() or N == 0 or F == 0 or D == 0:
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

    # One matmul over the WHOLE catalog: (N*F, D) · (D,) → (N*F,) → (N, F)
    sims = (matrix.reshape(N * F, D) @ q).reshape(N, F)
    sims = np.clip(sims, -1.0, 1.0).astype(np.float64)

    # Raw best-field cosine per song — the absolute similarity used by
    # QUERY_SCORE_FLOOR. Invalid fields are masked out so they can't win.
    raw_max = np.where(valid, sims, -np.inf).max(axis=1)

    # Per-field mean across the full catalog (masking missing fields so
    # they don't drag the mean toward 0). Independent of song_ids — same
    # query → same mean, regardless of which chips ran before.
    counts = valid.sum(axis=0).clip(min=1)
    field_mean = np.where(valid, sims, 0.0).sum(axis=0) / counts
    centered = sims - field_mean
    centered = np.where(valid, centered, -np.inf)
    raw_scores = centered.max(axis=1)

    # Min-max into [0, 1] over the catalog so the percentile threshold
    # uses a fixed scale across chips.
    s_min, s_max = float(raw_scores.min()), float(raw_scores.max())
    spread = s_max - s_min
    if spread > 1e-6:
        norm_scores = (raw_scores - s_min) / spread
    else:
        norm_scores = np.full_like(raw_scores, 0.5)

    # Genre-centroid bonus over the catalog's top leaders. Computed once
    # per query (no dependence on subset) so it can't snowball when chips
    # narrow the alive set toward one artist's dominant genre.
    if genre_matrix is not None and genre_valid is not None and N > 0:
        if genre_valid.any():
            k = min(25, N)
            leader_idx = np.argpartition(-norm_scores, k - 1)[:k]
            leader_G  = genre_matrix[leader_idx]
            leader_V  = genre_valid[leader_idx]
            if leader_V.any():
                centroid = leader_G[leader_V].sum(axis=0)
                c_norm = float(np.linalg.norm(centroid))
                if c_norm > 1e-9:
                    centroid = centroid / c_norm
                    bonus = np.clip(genre_matrix @ centroid, 0.0, 1.0)
                    bonus = np.where(genre_valid, bonus, 0.0)
                    boosted = norm_scores + GENRE_WEIGHT * bonus
                    b_min, b_max = float(boosted.min()), float(boosted.max())
                    bspread = b_max - b_min
                    if bspread > 1e-6:
                        norm_scores = (boosted - b_min) / bspread
                    else:
                        norm_scores = boosted

    # Compute discriminability: how much does the best song stand above the
    # typical one? Robust to outliers (a few strong matches lift it; a few
    # very-weak matches don't). When the spread is wide (cliff query like
    # "oques grasses") this is 1.0; when scores are tight (uninformative
    # query like "música") it drops, dimming the entire visualisation.
    finite_mask = np.isfinite(raw_max)
    if int(finite_mask.sum()) >= 2:
        rmax_finite = raw_max[finite_mask]
        contrast = float(max(0.0, rmax_finite.max() - np.median(rmax_finite)))
        discriminability = max(
            QUERY_DISCRIM_FLOOR,
            min(1.0, contrast / QUERY_DISCRIM_REF),
        )
    else:
        discriminability = QUERY_DISCRIM_FLOOR

    # Salience drives opacity / colour: it dims the entire viz when the
    # query is uninformative. Rank (= norm_scores, untouched by
    # discriminability) drives point SIZE so even a poor query still
    # shows which songs are *relatively* the best ones — without rank,
    # uninformative queries would render every point too small to read.
    salience = norm_scores * discriminability

    in_subset = np.zeros(N, dtype=bool)
    in_subset[sub_idx] = True
    subset_indices = np.where(in_subset)[0]
    if subset_indices.size == 0:
        return []

    order = np.argsort(-salience[subset_indices], kind="stable")
    ordered = subset_indices[order]
    # Bulk numpy → Python conversion. Faster than the per-element
    # int()/float()/round() loop because .tolist() converts the whole
    # array in C, and the cost matters when this is called on ~5000 rows.
    ids  = ordered.tolist()
    sals = np.round(salience[ordered],    4).tolist()
    rnks = np.round(norm_scores[ordered], 4).tolist()
    return list(zip(ids, sals, rnks))


def filter_by_similarity_fast(
    focal_id: int,
    song_ids: list[int] | None,
    index: dict,
    percentile: float = SIMILAR_PERCENTILE,
) -> list[tuple[int, float]]:
    """Vectorised song-to-song similarity filter over the dense visible index.

    Acts as a *filter*, not a top-k: returns every song whose similarity to
    the focal is above ``percentile`` of the normalised score, so the chip
    behaves like the query chip and stacking multiple chips composes
    naturally into "similar to all of these".

    Scoring and thresholding are **computed over the entire visible
    catalog**, never over ``song_ids``. ``song_ids`` only intersects the
    global survivors at the end. That keeps chip composition commutative
    and prevents the genre bonus from snowballing as the subset narrows.
    The focal song is always in the global survivor set, but if the
    caller's subset excludes it, the intersection drops it — at that
    point the user has explicitly filtered it out via another chip.
    """
    id_to_idx = index["id_to_idx"]
    focal_idx_full = id_to_idx.get(int(focal_id))
    if focal_idx_full is None:
        return []

    matrix = index["matrix"]   # (N, F, D)
    valid  = index["valid"]    # (N, F)
    N, F_total, D = matrix.shape
    if F_total == 0 or D == 0:
        return []

    if song_ids is None:
        sub_idx = np.arange(N, dtype=np.int64)
    else:
        sub_idx = np.asarray(
            [id_to_idx[i] for i in song_ids if i in id_to_idx],
            dtype=np.int64,
        )
    # Even if the subset is empty (e.g. previous chip wiped it), still
    # compute global similarity so we can fall back to "at least the focal
    # + one neighbour" when the intersection comes out empty.

    # Restrict to fields that actually exist in the matrix; preserves the
    # configured order so weighting stays predictable.
    use_fields = [f for f in SIMILAR_FIELDS if f < F_total]
    if not use_fields:
        return []

    focal_block = matrix[focal_idx_full, use_fields, :]      # (Fu, D)
    focal_valid = valid[focal_idx_full, use_fields]          # (Fu,)
    if not focal_valid.any():
        return []

    # Per-field cosine over the WHOLE catalog: candidate.field · focal.field.
    full_block = matrix[:, use_fields, :]                    # (N, Fu, D)
    full_valid = valid[:, use_fields]                        # (N, Fu)
    per_field = np.einsum("nfd,fd->nf", full_block, focal_block)
    per_field = np.clip(per_field, -1.0, 1.0).astype(np.float64)

    # Only fields valid on *both* sides count.
    field_mask = full_valid & focal_valid[None, :]
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

    field_top = np.where(field_mask, sims_pos, 0.0).max(axis=1)
    raw = self_weighted * (field_top ** SIMILAR_GATE_POWER)

    # Genre bonus computed over the whole catalog. Stable across chip order.
    genre_matrix = index["genre_matrix"]
    genre_valid  = index["genre_valid"]
    if (
        genre_matrix is not None
        and genre_valid is not None
        and genre_valid[focal_idx_full]
    ):
        focal_g = genre_matrix[focal_idx_full]
        bonus = np.clip(genre_matrix @ focal_g, 0.0, 1.0)
        bonus = np.where(genre_valid, bonus, 0.0)
        raw = raw + GENRE_WEIGHT * bonus

    # Pin focal at the top so it always sits in the global survivor set.
    raw[focal_idx_full] = float(raw.max()) + GENRE_WEIGHT + 1.0

    r_min, r_max = float(raw.min()), float(raw.max())
    spread = r_max - r_min
    if spread > 1e-6:
        norm_scores = (raw - r_min) / spread
    else:
        norm_scores = np.full_like(raw, 0.5)

    threshold = float(np.percentile(norm_scores, percentile))
    keep_global = norm_scores >= threshold
    keep_global[focal_idx_full] = True

    in_subset = np.zeros(N, dtype=bool)
    in_subset[sub_idx] = True
    keep = keep_global & in_subset

    if keep.sum() < 2:
        # Guarantee at least 2 survivors (focal if it's in subset, plus one
        # neighbour) so the chip never collapses the alive set on its own.
        sub_scores = np.where(in_subset, norm_scores, -np.inf)
        order = np.argsort(-sub_scores)
        for j in order:
            if not np.isfinite(sub_scores[int(j)]):
                break
            keep[int(j)] = True
            if keep.sum() >= 2:
                break

    survivors = [
        (int(i), float(round(norm_scores[i], 4)))
        for i in np.where(keep)[0]
    ]
    survivors.sort(key=lambda t: t[1], reverse=True)
    return survivors


def compute_cercador_suggestions(
    query_text: str,
    index: dict,
    exclude_ids: set[int] | None = None,
    exclude_artist_names: set[str] | None = None,
    suggestions_k: int = config.CERCADOR_SUGGESTIONS_K,
    lyrics_extra_k: int = config.CERCADOR_LYRICS_EXTRA_K,
) -> dict:
    """Embedding-based smart-suggestions companion to /api/cercador.

    One query encoding is reused across three independent slots; one
    stacked matmul computes every field cosine for every song. The
    three slots, summarised:

    +----------------+----------------------------+----------------------+----------+
    | slot           | fields scored              | combination          | floor    |
    +================+============================+======================+==========+
    | suggestions    | lyrics, qualitative, title | max + per-field      | 0.40     |
    |                | (SUGGESTION_FIELDS)        | mean centering       |          |
    +----------------+----------------------------+----------------------+----------+
    | lyrics_extra   | ALL 5 fields               | max (raw, no center) | 0.40     |
    |                | (lyrics, qual, title,      |                      |          |
    |                |  album, artist)            |                      |          |
    +----------------+----------------------------+----------------------+----------+
    | group_extra    | embedded_artist ONLY       | argmax (single field,| 0.60     |
    |                | (ARTIST_FIELD_IDX = 4)     | deduped by name)     |          |
    +----------------+----------------------------+----------------------+----------+

    * **suggestions** — top up-to-``suggestions_k`` songs ranked by max
      over the SUGGESTION_FIELDS cosines, each field mean-centered across
      the visible set (mirrors what ``filter_embeddings_fast`` does on
      /api/filter). Artist and album are excluded — artist has its own
      ``group_extra`` slot, and album is too noisy. Title is included
      so the embedding can match conceptually-close song names that
      don't share surface words with the query (which the lexical
      engine cannot reach). Mean-centering removes each field's
      common-mode bias (the template "La cançó X de Y evoca temes
      principals…" cancels out), so the max picks the field that
      actually got the query rather than the field with the heaviest
      template prior.
    * **lyrics_extra** — top up-to-``lyrics_extra_k`` songs ranked by
      max over ALL fields (raw, not centered), with ``exclude_ids`` and
      the same 0.40 floor applied. Appended to the lexical Cançons
      column so the user sees embedding-discovered matches the keyword
      index missed; raw all-fields max is intentional here because the
      slot's purpose is "rescue lexical misses" (a strong artist/title
      cosine probably means a normalisation the cercador couldn't reach).
    * **group_extra** — top 1 artist name by cosine on the
      ``embedded_artist`` field, deduped (same-artist rows share the same
      vector), with ``exclude_artist_names`` filtered out and a SEPARATE
      higher floor (``GROUP_SUGGESTION_COSINE_FLOOR = 0.60``). The artist
      field is just bge-m3's encoding of the *name string* — no semantic
      info about the music — so below 0.60 cosines are mostly incidental
      letter overlap, not real matches. Length 0 or 1.

    Returns ``(row_idx, raw_cosine)`` pairs for the song-based slots and
    ``(artist_name, raw_cosine)`` for ``group_extra``. ``raw_cosine`` is
    the best-field cosine (clamped to [0, 1] by the route layer) so the
    frontend's "% match" reflects the actual closest field, not a centered
    value. Empty lists on encoder failure or empty matrix.
    """
    matrix = index["matrix"]   # (N, F, D), L2-normalised
    valid  = index["valid"]    # (N, F)
    if matrix.size == 0:
        return {"suggestions": [], "lyrics_extra": [], "group_extra": []}

    N, F, D = matrix.shape
    if F == 0 or D == 0:
        return {"suggestions": [], "lyrics_extra": [], "group_extra": []}

    try:
        q = np.asarray(encode_query(query_text), dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Suggestions: encoder unavailable (%s)", exc)
        return {"suggestions": [], "lyrics_extra": [], "group_extra": []}

    q_norm = float(np.linalg.norm(q))
    if q_norm < 1e-12:
        return {"suggestions": [], "lyrics_extra": [], "group_extra": []}
    q = q / q_norm

    # One matmul → every (song, field) cosine in (N, F).
    field_sims = (matrix.reshape(N * F, D) @ q).reshape(N, F).astype(np.float64)
    # Used by both passes to mask excluded ids.
    excluded_pos: list[int] = []
    if exclude_ids:
        id_to_idx = index["id_to_idx"]
        excluded_pos = [id_to_idx[i] for i in exclude_ids if i in id_to_idx]

    # ── Suggestions: max over (lyrics, qualitative_description) with
    # per-field mean centering. Title/artist/album are excluded by
    # restricting to SUGGESTION_FIELDS.
    suggestions: list[tuple[int, float]] = []
    sug_fields = [f for f in SUGGESTION_FIELDS if f < F]
    if sug_fields:
        sims = field_sims[:, sug_fields]          # (N, k) raw cosines
        v    = valid[:, sug_fields]               # (N, k) per-field validity

        # Per-field mean across valid songs — removes the field-level
        # common-mode (the template prior on qualitative_description, the
        # general Catalan-vocabulary prior on lyrics) so they're comparable.
        counts     = v.sum(axis=0).clip(min=1)
        field_mean = np.where(v, sims, 0.0).sum(axis=0) / counts
        centered   = np.where(v, sims - field_mean, -np.inf)
        ranking    = centered.max(axis=1)         # (N,) used for ordering

        # Absolute floor uses RAW cosine, not centered, so we keep only
        # songs that genuinely cosine-match the query in some field.
        raw_max = np.where(v, sims, -np.inf).max(axis=1)  # (N,)

        keep = np.isfinite(ranking) & (raw_max >= SUGGESTION_COSINE_FLOOR)
        for pos in excluded_pos:
            keep[pos] = False

        n_keep = int(keep.sum())
        if n_keep > 0:
            ranking_masked = np.where(keep, ranking, -np.inf)
            k = min(suggestions_k, n_keep)
            top = np.argpartition(-ranking_masked, k - 1)[:k]
            top = top[np.argsort(-ranking_masked[top])]
            suggestions = [
                (int(i), float(raw_max[i]))
                for i in top
                if np.isfinite(ranking_masked[i])
            ]

    # ── Lyrics extra: max over ALL fields (raw), with exclude_ids and
    # the absolute floor. These are "lexical engine missed it" rescues,
    # so we don't restrict to SUGGESTION_FIELDS — a strong title/artist
    # cosine here means the lexical match missed it (probably a typo or
    # an unusual normalisation), which is exactly what we want to surface.
    full_sims = np.where(valid, field_sims, -np.inf)
    max_sims = full_sims.max(axis=1)              # (N,)
    for pos in excluded_pos:
        max_sims[pos] = -np.inf

    keep_extra = np.isfinite(max_sims) & (max_sims >= SUGGESTION_COSINE_FLOOR)
    lyrics_extra: list[tuple[int, float]] = []
    n_keep_extra = int(keep_extra.sum())
    if n_keep_extra > 0:
        masked_extra = np.where(keep_extra, max_sims, -np.inf)
        k2 = min(lyrics_extra_k, n_keep_extra)
        top2 = np.argpartition(-masked_extra, k2 - 1)[:k2]
        top2 = top2[np.argsort(-masked_extra[top2])]
        lyrics_extra = [
            (int(i), float(max_sims[i]))
            for i in top2
            if np.isfinite(masked_extra[i])
        ]

    # ── Group extra: top-1 unique artist by cosine on embedded_artist.
    # Same-artist songs share the artist string → share the artist vector,
    # so argmax over the column directly identifies the top artist; the
    # route layer dedupes against names already shown in the lexical
    # Grups column via ``exclude_artist_names``.
    group_extra: list[tuple[str, float]] = []
    if ARTIST_FIELD_IDX < F:
        artist_sims  = field_sims[:, ARTIST_FIELD_IDX]
        artist_valid = valid[:, ARTIST_FIELD_IDX]
        artist_masked = np.where(artist_valid, artist_sims, -np.inf)
        if exclude_artist_names:
            songs_meta = index["songs"]
            for i, s in enumerate(songs_meta):
                name = (s.get("artist") or "").strip()
                if name and name in exclude_artist_names:
                    artist_masked[i] = -np.inf
        # Deduplicate by artist name, then return top-3 above the floor.
        seen_artists: set[str] = set()
        songs_meta = index["songs"]
        for idx in np.argsort(-artist_masked):
            cos = float(artist_masked[idx])
            if cos < GROUP_SUGGESTION_COSINE_FLOOR or not np.isfinite(cos):
                break
            name = (songs_meta[int(idx)].get("artist") or "").strip()
            if name and name not in seen_artists:
                seen_artists.add(name)
                group_extra.append((name, cos))
                if len(group_extra) >= 3:
                    break

    return {
        "suggestions":  suggestions,
        "lyrics_extra": lyrics_extra,
        "group_extra":  group_extra,
    }


def compute_group_extra(
    q: np.ndarray,
    index: dict,
    exclude_artist_names: set[str] | None = None,
) -> list[tuple[str, float]]:
    """Return the top-1 artist match using the pre-computed query vector.

    Cheaper than ``compute_cercador_suggestions`` when Qdrant handles the
    song slots and we only need the group_extra — does a single artist-column
    matmul instead of the full (N, F, D) pass.

    Args:
        q: L2-normalised float32 query vector (MODEL_DIM,).
        index: Visible-song index from ``data_loader.get_visible_index()``.
        exclude_artist_names: Artists already shown in the lexical column.

    Returns:
        List of 0 or 1 ``(artist_name, raw_cosine)`` tuples.
    """
    matrix = index.get("matrix")
    valid  = index.get("valid")
    if matrix is None or matrix.size == 0:
        return []

    N, F, D = matrix.shape
    if ARTIST_FIELD_IDX >= F:
        return []

    artist_vecs   = matrix[:, ARTIST_FIELD_IDX, :]   # (N, D)
    artist_valid  = valid[:, ARTIST_FIELD_IDX]        # (N,)
    artist_sims   = artist_vecs @ q                   # (N,)
    artist_masked = np.where(artist_valid, artist_sims, -np.inf)

    if exclude_artist_names:
        songs_meta = index.get("songs", [])
        for i, s in enumerate(songs_meta):
            name = (s.get("artist") or "").strip()
            if name and name in exclude_artist_names:
                artist_masked[i] = -np.inf

    if not np.isfinite(artist_masked).any():
        return []

    songs_meta = index.get("songs") or []
    seen_artists: set[str] = set()
    results: list[tuple[str, float]] = []
    for idx in np.argsort(-artist_masked):
        cos = float(artist_masked[idx])
        if cos < GROUP_SUGGESTION_COSINE_FLOOR or not np.isfinite(cos):
            break
        name = (songs_meta[int(idx)].get("artist") or "").strip()
        if name and name not in seen_artists:
            seen_artists.add(name)
            results.append((name, cos))
            if len(results) >= 3:
                break
    return results


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
    bonus = _genre_bonus(focal_song.get("genre_profile"), songs)
    combined = sims + GENRE_WEIGHT * bonus

    scored = [
        {**song, "score": round(float(combined[i]), 4)}
        for i, song in enumerate(songs)
        if i != focal_idx
    ]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return [{**focal_song, "score": 1.0}] + scored[:n]
