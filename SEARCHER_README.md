# Searcher Pipeline — Technical Documentation

This document explains the full search pipeline of the Semantic Song Search Engine: how a user query travels from the frontend to the backend, gets processed, and returns results to the visualization.

---

## Architecture Overview

```
Frontend (React + Vite)          Backend (FastAPI + Python)
┌─────────────────────┐          ┌──────────────────────────────┐
│  FilterBar (chips)   │──POST──▶│  /api/filter                 │
│  Scatter2D (canvas)  │◀────────│    → filter_embeddings()     │
│  TopResults (list)   │         │    → scores + alive IDs      │
│                      │         │                              │
│  Click song          │──POST──▶│  /api/neighbors              │
│                      │◀────────│    → build_neighborhood()    │
│                      │         │    → cosine similarity IDs   │
│                      │         │                              │
│  Initial load        │──GET───▶│  /api/songs                  │
│                      │◀────────│    → all songs + t-SNE proj  │
│                      │         │                              │
│  Cercador (instant)  │──GET───▶│  /api/cercador?q=...         │
│                      │◀────────│    → fuzzy matched results   │
└─────────────────────┘          └──────────────────────────────┘
```

---

## File Map

### Backend (`app/backend/`)

| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI app entry point. CORS config. Pre-loads embedding model on startup via `lifespan`. |
| `api/routes/search.py` | Core endpoints: `/api/songs`, `/api/filter`, `/api/neighbors`, `/api/songs/{id}`. |
| `api/routes/cercador.py` | Instant search endpoint `/api/cercador` with fuzzy matching. |
| `api/schemas.py` | Pydantic request/response models for all endpoints. |
| `core/encoder.py` | Embedding model wrapper (`multilingual-e5-small`). Query and passage encoding. |
| `core/embeddings.py` | Semantic filtering (`filter_embeddings`) and neighborhood building (`build_neighborhood`). |
| `core/projections.py` | t-SNE 2D/3D computation and MDS neighborhood layout. Caches full-dataset projections. |
| `core/data_loader.py` | Loads songs from `data/mock_songs.json`. In-memory cache. |
| `data/mock_songs.json` | 50 Catalan songs with metadata + pre-computed 384-dim embeddings. |
| `data/mock_noticies.json` | Mock news articles for the cercador. |

### Frontend (`app/frontend/src/`)

| File | Purpose |
|------|---------|
| `App.jsx` | Main orchestrator. Manages page routing, data state, chip filters, similarity mode. |
| `App.css` | All component styles (1300+ lines). |
| `api/client.js` | Axios wrapper with endpoints: `fetchAllSongs`, `filterSongs`, `fetchNeighbors`, `cercadorSearch`. |
| `hooks/useTheme.js` | Light/dark theme hook with localStorage persistence. |
| `components/FilterBar.jsx` | Chip-based filter input. Users type + enter to add filters that stack. |
| `components/TopResults.jsx` | Ranked song list in the left panel, sorted by score. |
| `components/SongDetail.jsx` | Modal popup with full song metadata and lyrics. |
| `components/VizSelector.jsx` | Toggle between 2D / 3D / Navigation views. |
| `components/WelcomePage.jsx` | Landing page with "Descobreix" and "Cerca" buttons. |
| `components/CercadorPage.jsx` | Instant search page with debounced fuzzy matching. |
| `components/ThemeToggle.jsx` | Light/dark mode button. |
| `components/visualizations/Scatter2D.jsx` | Canvas-based 2D scatter. Always shows all songs, dims non-active ones. |
| `components/visualizations/Scatter3D.jsx` | Three.js 3D sphere visualization. |
| `components/visualizations/Navigation2D.jsx` | Isometric city grid visualization. |
| `components/visualizations/genreColors.js` | Genre → hex color mapping. |

---

## Pipeline 1: Semantic Filtering (Chip Filters)

This is the main search pipeline. Users type queries that stack as filters.

### Step-by-step flow

1. **User types a query** in the `FilterBar` and presses Enter.
2. **Frontend** calls `POST /api/filter` with `{ query, song_ids }`:
   - `song_ids` is the list of currently alive song IDs (from previous filters), or `null` for the first filter.
3. **Backend** (`search.py → filter_songs()`):
   - If `song_ids` provided, fetches only those songs from `data_loader.get_songs_by_ids()`.
   - Otherwise fetches all songs from `data_loader.load_all_songs()`.
   - Calls `embeddings.filter_embeddings(query, songs)`.
4. **`filter_embeddings()`** (`core/embeddings.py`):
   - Calls `encoder.encode_query(query)` to get a 384-dim vector.
   - Computes cosine similarity between query vector and every song's pre-computed embedding.
   - Min-max normalizes scores to [0, 1] (critical because raw cosine values cluster tightly for same-domain content).
   - Applies 70th percentile threshold: keeps top ~30% of songs.
   - Returns survivors sorted by score, each with a `score` field.
5. **`encode_query()`** (`core/encoder.py`):
   - Loads `intfloat/multilingual-e5-small` model (cached after first load).
   - Prepends `"query: "` prefix to the text.
   - Tokenizes, runs through transformer, mean-pools token embeddings.
   - L2-normalizes the result → 384-dim unit vector.
6. **Frontend** receives the response:
   - Stores the alive IDs and score map.
   - The `Scatter2D` visualization dims non-active songs and scales active songs by score.
   - The `TopResults` panel shows the active songs sorted by score.
   - The chip appears in the filter bar.

### Progressive filtering

Each new chip filter restricts the search to the surviving songs from the previous filter:

```
All 50 songs
  ├── Chip "amor" → filter → 15 survivors (top 30%)
  │   ├── Chip "tristesa" → filter 15 → 5 survivors
  │   │   └── Chip "folk" → filter 5 → 2 survivors
```

Removing a chip re-applies all remaining chips from scratch.

### Fallback (dimension mismatch)

If the song embeddings have a different dimension than the model output (e.g., mock 32-dim data vs. real 384-dim), the system falls back to a word-overlap scorer:
- Counts how many query words appear in the song's text fields.
- Uses median threshold instead of percentile.

---

## Pipeline 2: Similarity Exploration (Song Click)

When a user clicks a song in the scatter plot, the system finds songs similar to it.

### Step-by-step flow

1. **User clicks a song** in `Scatter2D`.
2. **Frontend** calls `POST /api/neighbors` with `{ song_id, n: 20 }`.
3. **Backend** (`search.py → get_song_neighbors()`):
   - Calls `embeddings.build_neighborhood(focal_id, all_songs, n=20)`.
4. **`build_neighborhood()`** (`core/embeddings.py`):
   - Calls `get_nearest_neighbors(focal_id, songs, n)`.
   - Assigns roles: `"focal"` (the clicked song), `"neighbor"` (similar songs).
5. **`get_nearest_neighbors()`**:
   - Computes cosine similarity between the focal song's embedding and every other song's embedding.
   - Sorts by similarity descending.
   - Returns focal (score=1.0) + top N neighbors with their scores.
6. **Frontend** receives the response:
   - Sets activeIds = focal + neighbor IDs.
   - Builds scoreMap from the response scores.
   - `Scatter2D` dims all non-neighbor songs, shows neighbors scaled by similarity.
   - The focal song is rendered as a diamond shape.

### Double-click for details

Double-clicking a song opens the `SongDetail` modal instead of exploring neighbors.

---

## Pipeline 3: Instant Search (Cercador)

A separate search interface for quick lookups, inspired by Viasona's search bar.

### Step-by-step flow

1. **User types** in the `CercadorPage` input.
2. **Frontend** debounces (150ms) then calls `GET /api/cercador?q=query`.
3. **Backend** (`cercador.py → cercador_search()`):
   - Lazy-loads a `CatalanSongQueryParser` from the `searchoptimal` module.
   - Parser performs fuzzy matching + spell correction.
   - Searches across three categories:
     - **Grups (Artists)**: accent-insensitive substring match on artist names.
     - **Cançons (Songs)**: matches on title, artist, lyrics snippet.
     - **Notícies (News)**: matches on article titles.
   - Returns max 5 grups, 8 cançons, 5 notícies.
   - Includes spell correction suggestions if the query was corrected.
4. **Frontend** renders results in a categorized dropdown.

### Fuzzy matching

`_normalize_for_match()` strips accents and special characters (e.g., `·` in Catalan) for accent-insensitive substring matching. Both the query and target text are normalized before comparison.

---

## Embedding Model Details

| Property | Value |
|----------|-------|
| Model | `intfloat/multilingual-e5-small` |
| Dimension | 384 |
| Supports | 100+ languages (including Catalan) |
| Query prefix | `"query: "` |
| Passage prefix | `"passage: "` |

### Song passage format

Each song is embedded as:
```
"passage: {title} by {artist}. Genre: {genre}. {lyrics_snippet}"
```

Embeddings are pre-computed and stored in `mock_songs.json`. To regenerate after changing the passage format or model, run:
```bash
python scripts/reembed_mock_songs.py
```

---

## Projection Methods

### t-SNE (full dataset)

Used for the initial scatter plot showing all songs. Computed once on startup and cached.

- **Algorithm**: t-SNE from scikit-learn
- **Perplexity**: min(30, n-1)
- **Init**: PCA (if n >= n_components) or random
- **Random state**: 42 (deterministic)
- **Cached**: yes, computed once per process lifetime

### Metric MDS (neighborhood)

Used when exploring song neighborhoods. Places the focal song at the origin and neighbors around it based on cosine distances.

- **Algorithm**: Metric MDS from scikit-learn with precomputed distance matrix
- **Distance**: 1 - cosine_similarity
- **Centering**: Focal song always at origin
- **Scaling**: 75th percentile non-focal distance = 1.0
- **Rotation**: Procrustes alignment to preserve travel direction from previous step

---

## Key Functions Reference

### `filter_embeddings(query_text, songs)` — `core/embeddings.py`
Main semantic filter. Encodes query, computes cosine similarities, applies 70th percentile threshold. Returns survivors with scores.

### `build_neighborhood(focal_id, all_songs, n, ...)` — `core/embeddings.py`
Builds neighborhood set for exploration. Finds N nearest neighbors, assigns roles (focal/neighbor/previous/bridge).

### `get_nearest_neighbors(focal_id, songs, n)` — `core/embeddings.py`
Computes cosine similarity between focal song and all others. Returns sorted list with scores.

### `compute_similarity(query_emb, song_emb)` — `core/embeddings.py`
Cosine similarity between two vectors. L2-normalizes both before dot product.

### `encode_query(text)` — `core/encoder.py`
Encodes user query with the e5 model. Prepends "query: " prefix. Returns 384-dim L2-normalized vector.

### `encode_passages(texts)` — `core/encoder.py`
Batch encodes passage strings. Used by the pre-embedding script.

### `load_encoder()` — `core/encoder.py`
Loads and caches the transformer model. First call takes ~60-90s on CPU.

### `compute_tsne_2d(songs)` / `compute_tsne_3d(songs)` — `core/projections.py`
Run t-SNE on song embeddings. Handle edge cases (n ≤ 3).

### `compute_neighborhood_2d(songs, focal_id, ...)` — `core/projections.py`
MDS layout for neighborhoods. Centers on focal, applies Procrustes rotation for visual continuity.

### `get_all_projections_2d()` / `get_all_projections_3d()` — `core/projections.py`
Cached full-dataset t-SNE projections. Computed once, returned for all subsequent calls.

### `load_all_songs()` — `core/data_loader.py`
Loads all songs from JSON. Cached in memory.

### `get_song_by_id(id)` / `get_songs_by_ids(ids)` — `core/data_loader.py`
Song lookup by ID. Linear scan on cached list.

---

## Running the System

### Backend
```bash
cd /path/to/semantic-song-search-engine
source .venv/bin/activate
python -m uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

First startup takes ~60-90s while the embedding model loads.

### Frontend
```bash
cd app/frontend
npm run dev
```

The Vite dev server proxies `/api` requests to `http://127.0.0.1:8000`.
