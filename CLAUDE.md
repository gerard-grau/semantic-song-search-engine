# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Semantic search engine for Catalan songs (Viasona catalog). Users type natural-language queries; the app filters the catalog progressively by cosine similarity over multi-field embeddings, visualizing the active set on a 2D map.

Two parallel search experiences live in the same FastAPI app:
- **Descobridor** — semantic, embedding-based. Endpoints: `GET /api/songs`, `GET /api/songs/{song_id}`, `POST /api/filter`, `POST /api/neighbors`.
- **Cercador** — instant text search with typo correction over songs/groups/news. Endpoints: `GET /api/cercador` (lexical), `GET /api/cercador/suggestions` (embedding-based extras).

Existing technical documentation (in Catalan) lives in `Documentacio/01_visio_general.md` … `Documentacio/05_searchoptimal.md`. Parts of it are stale on a few specifics — when in doubt about model/dims/file layout, trust the source files listed below.

## Commands

### Backend (Python 3.11+, run from repo root with `.venv` active)

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Run API (reads precomputed parquets — fast)
python -m uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000

# Force regeneration of artefacts before serving
RECOMPUTE_2D=1   python -m uvicorn app.backend.api.main:app ...   # rebuild embedded_songs_2d.parquet
RECOMPUTE_META=1 python -m uvicorn app.backend.api.main:app ...   # rebuild songs_meta.parquet

# Build every data artefact in one shot (idempotent — skips outputs that exist)
.venv/bin/python -m data_pipeline.execute_all
.venv/bin/python -m data_pipeline.execute_all --force                # rebuild everything
.venv/bin/python -m data_pipeline.execute_all --method tsne          # use t-SNE instead of UMAP
.venv/bin/python -m data_pipeline.execute_all --genre-mode none      # disable genre clustering bias

# Run an individual step (each lives in data_pipeline/stepN_*.py)
.venv/bin/python -m data_pipeline.step1_fetch_catalogue_csvs --force
.venv/bin/python -m data_pipeline.step2_build_top_songs      --force
.venv/bin/python -m data_pipeline.step3_filter_top5000_embeddings --force
.venv/bin/python -m data_pipeline.step4_build_genres_parquet --force
.venv/bin/python -m data_pipeline.step5_build_meta           --force
.venv/bin/python -m data_pipeline.step6_project_2d           --force
```

Swagger UI at `http://127.0.0.1:8000/docs`. Health probe at `GET /`.

### Frontend (Node 18+)

```bash
cd app/frontend
npm install
npm run dev          # http://localhost:3000 (proxies /api → 127.0.0.1:8000)
npm run build
npm run lint         # ESLint flat config
```

### Tests

`tests/test_classic/`, `tests/test_smart/`, `tests/test_performance/` currently contain placeholders only — there is no working test suite.

## Architecture

### Two-process layout

React (Vite, port 3000) ──axios──▶ Vite proxy `/api` ──▶ FastAPI (port 8000)

The frontend never reads data files directly. All app state lives in `App.jsx` (no router, no context); navigation between welcome / main / cercador is a `page` string.

### Backend hot path: `/api/filter`

The `/api/filter` endpoint is the dominant performance constraint. The lifespan handler in `app/backend/api/main.py` **prewarms everything it touches before serving traffic**:

1. Reads small precomputed parquets (`load_visible_songs`, `get_all_projections_2d`).
2. Builds the dense visible index — an `(N, F, D)` float32 cube of L2-normalized per-field embeddings (N≈5000 visible songs, F=5 fields, D=1024). See `data_loader.get_visible_index`. ~100 MB.
3. Loads the encoder (`BAAI/bge-m3`) and runs one dummy `encode_query` to JIT the first forward pass.

After warmup, every `/api/filter` call is one encoder forward pass + one matmul on a row slice of the cube. No t-SNE is run per query — the frontend reuses the precomputed 2D layout and dims/highlights points by id.

### Data pipeline (offline → online)

All offline data generation lives in `data_pipeline/`. The data directory
is split into two subfolders:

```
app/backend/data/
├── raw/         — external inputs (manual drops + DB dumps)
└── processed/   — pipeline-derived artefacts (safe to delete & rebuild)
```

Files that must exist in `raw/` before the pipeline runs:

* `augmented_songs.csv`     — full song table (manual export)
* `embedded_songs.parquet`  — per-field bge-m3 embeddings
                              (produced by `ml/embeddings/preembedding.py`)

Plus, outside `app/backend/data/`:

* `validacio/entrances_exits.csv`  — GA4 popularity export
* `.env`                           — MariaDB credentials (optional)

One command (`python -m data_pipeline.execute_all`) chains the six steps:

```
step1_fetch_catalogue_csvs.py   ──▶  raw/cancons.csv, raw/grups.csv, raw/noticies.csv
    (DB → CSVs; skipped if files already present, warns if DB unreachable.
     These land in raw/ because the content is a DB dump, not a transform.)

step2_build_top_songs.py        ──▶  processed/top_5000_songs.csv  (with genre column)
    (entrances_exits.csv + data_pipeline/_genres.py human-labeled dict)

step3_filter_top5000_embeddings.py  ──▶  processed/embedded_songs_top5000.parquet
    (two-pointer alignment over (id_lyrics, artist) → 5000 rows in popularity order)

step4_build_genres_parquet.py   ──▶  processed/embedded_songs_genres.parquet
    (one-hot per song from the genre column in top_5000_songs.csv)

step5_build_meta.py             ──▶  processed/songs_meta.parquet
    (augmented_songs.csv + cancons.csv ⨝ genres parquet)

step6_project_2d.py             ──▶  processed/embedded_songs_2d.parquet
    (UMAP/t-SNE, optionally genre-augmented)
```

Path constants live in `data_pipeline/_paths.py` (`RAW_DIR`, `PROCESSED_DIR`)
and are mirrored in `app/backend/core/data_loader.py` and
`app/backend/core/cercador_index.py`. `app/backend/data/` is gitignored —
the entire `raw/` and `processed/` trees are local-only.

There is no top-level `data/` directory; everything data-related lives
under `app/backend/data/`.

**Genres.** The taxonomy is six labels — `folk`, `cançó autor`,
`pop-rock`, `rumba`, `havanera`, `música urbana` — listed in
`data_pipeline/_genres.py`. The same six show up in
`app/frontend/src/components/visualizations/genreColors.js`; keep both in sync.

### Embedding model & scoring

`encoder.py` is the single source of truth for model config. Currently `BAAI/bge-m3` (1024-dim, CLS pooling, no prefixes). **If you change `MODEL_NAME`, `PASSAGE_PREFIX`, or `build_song_passage()`, you must regenerate `embedded_songs.parquet`** with `ml/embeddings/preembedding.py`. The API detects dimension mismatches and falls back to word-overlap scoring.

Two scoring modes share the visible index:
- **Text query** (`filter_embeddings_fast` in `embeddings.py`): max cosine across F=5 fields per song (multi-field late fusion: lyrics / qualitative description / title / album / artist). One forward pass for the query, one matmul.
- **Similarity-to-song** (`filter_by_similarity_fast`): self-weighted mean over (lyrics, description, title, artist) gated by `max(s_i)^0.5`. Constants `SIMILAR_FIELDS`, `SIMILAR_FIELD_POWER`, `SIMILAR_GATE_POWER` in `embeddings.py`. A small genre-profile bonus (`GENRE_WEIGHT=0.15`) is added when `embedded_songs_genres.parquet` is present.

After scoring, scores are min-max normalised and thresholded by percentile (70th for queries, 50th for similarity chips) to produce the survivor set.

### Cercador smart suggestions

The Cercador tab runs **two engines in parallel** on each keystroke:

1. **Lexical** — `/api/cercador` (parser2 + inverted indices, no embeddings) — fills the Grups / Cançons / Notícies columns.
2. **Embedding** — `/api/cercador/suggestions` (`compute_cercador_suggestions` in `embeddings.py`) — adds three independent slots, all sharing one query encoding and one matmul against the dense visible cube.

| Slot | Where it renders | Fields scored | Combination | Floor | Excludes |
|---|---|---|---|---|---|
| `suggestions` | "Suggerències" section (main 0–4) | `embedded_lyrics`, `embedded_qualitative_description`, `embedded_title` | **max** over fields with per-field mean centering (same fusion as `/api/filter`) | `SUGGESTION_COSINE_FLOOR = 0.40` raw cosine | — |
| `lyrics_extra` | appended to the lexical Cançons column (0–2) | **all 5** fields (lyrics, qualitative, title, album, artist) | **max** over fields, raw cosines | `SUGGESTION_COSINE_FLOOR = 0.40` | song ids already shown lexically |
| `group_extra` | appended to the lexical Grups column (0–1) | `embedded_artist` **only** | argmax (single field; same-artist songs share the vector) | `GROUP_SUGGESTION_COSINE_FLOOR = 0.60` | artist names already shown lexically |

Design notes:
- **`suggestions`** deliberately excludes album (same-album songs are trivially similar and not what the user asked) and artist (covered by `group_extra`). Title was added because the lexical engine only matches titles containing the query verbatim — embedding-matching catches conceptually-close titles that don't share surface words.
- **`lyrics_extra`** uses all 5 fields un-centered because its purpose is "rescue what the lexical engine missed" — a strong title/artist cosine here probably means a normalisation the cercador couldn't reach.
- **`group_extra`** has its own (higher) floor because `embedded_artist` is just bge-m3's encoding of the artist *name* as a string — no semantic info about the music, so anything below 0.60 is mostly incidental letter overlap. The displayed score on the UI is the raw cosine, clamped to [0, 1].
- Constants are top-of-file in `embeddings.py` (`SUGGESTION_FIELDS`, `SUGGESTION_COSINE_FLOOR`, `ARTIST_FIELD_IDX`, `GROUP_SUGGESTION_COSINE_FLOOR`).

### 2D projection augmentation

`data_pipeline.step6_project_2d` builds layout vectors as `concat(unit(text), alpha_genre * unit(genre_profile))` so songs cluster by genre. With both halves unit-norm, `alpha_genre² / (1 + alpha_genre²)` is genre's share of squared distance. Default `alpha_genre=2.0` ≈ 80% genre / 20% text. CLI flags: `--genre-mode {soft,onehot,none}`, `--alpha-genre`, `--method {umap,tsne,pca_umap}`, `--pca-dim`.

### `searchoptimal/parser2.py` and `core/cercador_index.py`

The cercador (instant search) has its own pipeline disjoint from embeddings:
- `searchoptimal/parser2.py` — Damerau-Levenshtein with QWERTY-aware substitution costs + `wordfreq` Zipf priors. Produces `{word: probability}` bags for queries.
- `app/backend/core/cercador_index.py` — inverted indices over `cancons.csv`, `grups.csv`, `noticies.csv`. Built once on first request; prewarmed in background after the embedding model loads.

The original `searchoptimal/parser.py` (tier-based, uses `symspellpy`) is **not** currently wired in — `cercador_index.py` imports `parser2`.

### Frontend filter composition

Filters are **chips** (`App.jsx`); each chip narrows the previous alive set. Two chip kinds compose freely:
- `{ kind: 'query',   value: string }` — text query, hits `POST /api/filter` with `query`.
- `{ kind: 'similar', value: songId }` — similar-to-song, hits `POST /api/filter` with `similar_to_id`.

Removing any chip re-runs the remaining chips from scratch (no partial cache). Survivor combined score is the arithmetic mean of per-chip scores. `Scatter2D.jsx` always renders the precomputed 2D points and dims inactive ids.

### Visible-song cap

`data_loader.VISIBLE_SONG_LIMIT = 5000` caps what the UI sees and what `/api/filter` scores against (`load_visible_songs` returns this set in row order of `embedded_songs_2d.parquet`). `load_all_songs` is the wider catalog (everything in `embedded_songs.parquet`) used only by `/api/neighbors` when `song_ids` is not provided.

## Conventions

- Default to **Catalan** for any user-facing strings and `Documentacio/` (this is a Catalan-music project — see existing copy in `WelcomePage.jsx`, `FilterBar.jsx`, etc.).
- Pydantic models in `app/backend/api/schemas.py` are the contract with the frontend. When you change one, update `app/frontend/src/api/client.js` and consumers in the same change.
- `app/backend/core/similarity.py` is the only place that normalizes/cosines; `embeddings.py` and `projections.py` delegate. Don't add a fourth copy.
- Caches live as module globals. After regenerating a parquet, call `invalidate_cache()` on the relevant module (the `RECOMPUTE_*` env flags do this for you).

## Known dead/legacy code

The following exist but aren't imported anywhere in the active path:
- `app/backend/core/get_songs.py` — old DB getter with hardcoded credentials and mojibake.
- `app/backend/core/retrieval_functions.py` — old `id2emb` helpers.
- `app/frontend/src/components/SearchBar.jsx`, `SongShowcase.jsx` — not referenced from `App.jsx`.
- `searchoptimal/parser.py` (the tier-based one) — `cercador_index.py` uses `parser2.py` instead.
- Multiple `README_*.md` at the repo root (BERNAT, 2, CERCADOR, DATA, WINDOWS, SEARCHER) — older drafts. Authoritative docs are `Documentacio/` and `README_LINUX.md` (Linux/Mac setup) / `README_WINDOWS.md` (Windows setup).
