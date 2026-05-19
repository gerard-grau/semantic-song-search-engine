"""
config.py — single source of truth for tunable parameters.

Every knob that's worth experimenting with from outside the code lives here.
Edit this file directly to change defaults; CLI flags on the pipeline scripts
(e.g. ``--alpha-genre``) still override these values for one-off runs.

Deliberately NOT in this file:

* ``MODEL_NAME``, ``MODEL_DIM``, ``PASSAGE_PREFIX`` — kept in
  ``app/backend/core/encoder.py`` because changing them is a coupled change
  with ``embedded_songs.parquet`` (you must regenerate the parquet with
  ``ml/embeddings/preembedding.py`` after editing). Locking them next to
  the parquet they were built against prevents silent drift.

* Internal parquet ``batch_size`` values — implementation detail, no user
  benefit to expose.

* The Cercador stopword list (``_STOPWORDS`` in cercador_index.py) — a
  closed-form list of Catalan function words, not a knob.

Sections below mirror the layout of the codebase.
"""

from __future__ import annotations


# ============================================================================
# Pipeline — defaults for the offline data-generation steps.
# CLI flags (--method, --alpha-genre, --top-n, ...) override these per run.
# ============================================================================

# step2_build_top_songs: how many songs go into top_5000_songs.csv.
# Changing this also changes how many rows steps 3-6 produce downstream.
PIPELINE_TOP_N = 5000

# step6_project_2d: 2D projection backend.
# One of: "umap", "tsne", "pca_umap".
PIPELINE_PROJECTION_METHOD = "umap"

# step6_project_2d: PCA pre-reduction for t-SNE / pca_umap (0 disables).
PIPELINE_PCA_DIM = 50

# step6_project_2d: how the genre block participates in the layout.
# One of: "soft" (per-song genre profile), "onehot" (single argmax),
#         "none" (text-only projection).
PIPELINE_GENRE_MODE = "soft"

# step6_project_2d: genre weight in the concatenated layout vector.
# Contribution to squared distance is exactly alpha² × text. alpha=2.0 ≈
# 80% genre / 20% text in squared-distance terms — visible genre clusters
# without erasing within-genre semantics.
PIPELINE_ALPHA_GENRE = 0.2


# ============================================================================
# Embedding scoring (app/backend/core/embeddings.py)
# ============================================================================

# Maximum genre bonus a song can earn on top of its [0, 1]-normalised text
# score. Genre nudges the ranking but never overrides the text signal.
GENRE_WEIGHT = 0.15

# Percentile cut-offs on normalised scores.
# QUERY_PERCENTILE — text-query chip keeps only the top ~10% so the scatter
# feels selective. SIMILAR_PERCENTILE — similar-to-song chip stays broad so
# stacking 3-4 chips intersects to a meaningful "similar to all of these" set.
QUERY_PERCENTILE = 90.0
SIMILAR_PERCENTILE = 50.0

# Song-to-song similarity scoring (filter_by_similarity_fast).
# Field columns are (lyrics, description, title, album, artist) — index 3
# (album) is skipped because same-album songs are trivially similar.
# Score = (Σ s_i^p / Σ s_i^(p-1)) × max(s_i)^g  — self-weighted mean gated
# by the top field. Higher power → top field dominates; higher gate power
# → low best-field collapses the score harder.
SIMILAR_FIELDS = (0, 1, 2, 4)
SIMILAR_FIELD_POWER = 4.0
SIMILAR_GATE_POWER = 0.5

# Cercador smart-suggestions embedding pass.
# SUGGESTION_FIELDS — fields scored for the main suggestions slot.
# Excludes album (noise) and artist (covered by group_extra channel).
SUGGESTION_FIELDS = (0, 1, 2)

# Absolute raw-cosine threshold for the suggestions / lyrics_extra slots.
# Songs whose best field cosine falls below this aren't shown — weak queries
# return 0–K results instead of always K mediocre ones.
SUGGESTION_COSINE_FLOOR = 0.40

# Per-song artist-embedding field index (matches EMBEDDING_FIELD_COLUMNS).
ARTIST_FIELD_IDX = 4

# Higher floor for the group-extra channel. The artist field is bge-m3's
# encoding of the artist's *name* as a string, with no semantic info about
# the music — anything below this is mostly incidental letter overlap.
GROUP_SUGGESTION_COSINE_FLOOR = 0.60

# Top-K limits for the two embedding-suggestion slots (the third slot,
# group_extra, returns 0–1 by construction).
CERCADOR_SUGGESTIONS_K = 4
CERCADOR_LYRICS_EXTRA_K = 2


# ============================================================================
# Visible data window (app/backend/core/data_loader.py)
# ============================================================================

# Hard cap on the songs the frontend visualizes at once. The full embedded
# catalog is still on disk — this only limits what's handed to the scatter.
VISIBLE_SONG_LIMIT = 5000


# ============================================================================
# Cercador lexical retrieval (app/backend/core/cercador_index.py)
# ============================================================================

# wordfreq-based dampener reference (per-million scale).
# Each scored token is multiplied by 1 / (1 + lex_freq / LEX_PENALTY_REF):
#   pel (per-million ~300+) → multiplier ~0.25
#   terra (~50)             → multiplier ~0.67
#   amor (~20)              → multiplier ~0.83
#   OOV/proper-nouns        → multiplier 1.0
CERCADOR_LEX_PENALTY_REF = 100

# BM25-style field weights — title/name fields beat snippets and lyrics.
CERCADOR_W_SONG_TITLE = 1.6
CERCADOR_W_SONG_ARTIST = 1.3
CERCADOR_W_SONG_LYRICS = 0.8
CERCADOR_W_GRUP_NAME = 1.6
CERCADOR_W_NOTI_TITLE = 1.6
CERCADOR_W_NOTI_SNIPPET = 0.4

# Additive boost when the (normalised) query exactly matches a stored
# phrase — surfaces "Sau" (the band) above songs containing "sau".
CERCADOR_EXACT_PHRASE_BOOST = 50.0

# Sentence-reconstruction beam search (used to catch "bog per tu" → boost
# the song "boig per tu" even when the literal query has typos).
CERCADOR_RECONSTRUCT_TOP_PER_WORD = 5      # per-word fan-out into the beam
CERCADOR_RECONSTRUCT_BEAM_K = 32           # max sentences kept per step
CERCADOR_RECONSTRUCT_MIN_JOINT_PROB = 0.05  # drop reconstructions below this

# Per-source top-K limits returned by /api/cercador.
CERCADOR_TOP_GRUPS = 5
CERCADOR_TOP_SONGS = 8
CERCADOR_TOP_NOTICIES = 5

# Phrase-edit-distance rerank (only fires for multi-token queries) —
# scored over the top N candidates of each collection.
CERCADOR_PHRASE_RERANK_TOP_N = 120
CERCADOR_PHRASE_RERANK_WEIGHT_TITLE = 18.0   # song title, group name, etc.
CERCADOR_PHRASE_RERANK_WEIGHT_ARTIST = 12.0  # song artist, noticia title

# Parser top-K per-word fuzzy candidates fed into the inverted-index scan.
CERCADOR_PARSER_TOP_K = 20


# ============================================================================
# Parser (app/backend/core/parser2.py)
# ============================================================================

# Damerau-Levenshtein operation costs (see parser2 module docstring).
PARSER_COST_SWAP = 0.5      # adjacent transposition (amro ↔ amor)
PARSER_COST_INSERT = 1.0    # input is missing a char
PARSER_COST_DELETE = 1.0    # input has an extra char
PARSER_COST_SUB_ADJ = 0.85  # substitution, keys adjacent on QWERTY
PARSER_COST_SUB_FAR = 1.5   # substitution, keys not adjacent
PARSER_COST_ACCENT = 0.1    # accent-only / fold-equivalent / middle-dot
PARSER_COST_SPACE = 2.0     # explicit space (splits handled separately)

# Probability shaping. p_raw = exp(-DECAY * d / L) * freq_factor(freq).
# Higher DECAY → far candidates lose more mass, input word dominates more.
PARSER_DECAY = 3.0

# Cost for a binary split (implicit missing-space edit).
PARSER_SPLIT_COST = 1.5

# Softmax temperature for per-word normalisation. Lower sharpens.
PARSER_SOFTMAX_T = 0.10

# Long-tail trim. Keep top-N + anything ≥ floor, then renormalise.
PARSER_KEEP_TOP_N = 5
PARSER_PROB_FLOOR = 0.20

# Floor on input-word raw probability before softmax (protects niche real
# words missing from wordfreq from being crushed by their alternates).
PARSER_INPUT_RAW_FLOOR = 0.20

# freq_factor saturation reference. log1p(f)/log1p(FREQ_REF) hits 1 here.
PARSER_FREQ_REF = 500.0

# Edit-distance budgets for single-word matches and full-phrase reranking.
PARSER_MAX_WORD_DISTANCE = 1.75
PARSER_MAX_PHRASE_DISTANCE = 4.0
