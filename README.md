# Semantic Song Search Engine

Prototype workspace for the Viasona challenge: a **hybrid search experience** with a traditional search list, an intelligent search list, and a map-based exploration panel.

The current implementation is intentionally a **UI/API scaffold** with mock data.

## Current objective

This repository now prioritizes a demonstrable prototype aligned with the challenge goals:

- top-level wide search input
- left panel with two ranked result sections
  - traditional results
  - intelligent results
- right panel with a visual map area for songs

Real search engines, ML ranking, and real map behavior are planned for later iterations.

## What is implemented now

### Frontend prototype

- Static web app focused on layout and interaction flow.
- Calls backend `GET /search` and renders:
  - traditional results list
  - intelligent results list
  - map points
- Falls back to built-in mock payload when backend is unavailable.

Location:

- [app/frontend](app/frontend)

### Backend prototype

- FastAPI mock service with deterministic test data.
- Stable endpoint for frontend integration.
- No database dependency in this phase.

Location:

- [app/backend](app/backend)

### Other project modules (kept)

- [youtube_audio_pipeline](youtube_audio_pipeline): YouTube audio feature extraction pipeline
- [etl](etl): ETL workspace (future implementation)
- [ml](ml): ML workspace (future implementation)
- [data](data): raw/processed storage
- [notebooks](notebooks): exploratory notebooks

## Repository structure (high level)

```text
app/
  backend/
  frontend/
data/
docs/
etl/
ml/
notebooks/
tests/
youtube_audio_pipeline/
```

## Local development

### Prerequisites

- Python 3.11+
- Optional virtual environment (`.venv`)
- `ffmpeg` only if you will run `youtube_audio_pipeline`

### 1) Setup Python environment

From repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run backend

From repository root:

```bash
uvicorn app.backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URLs:

- API base: `http://127.0.0.1:8000`
- docs: `http://127.0.0.1:8000/docs`
- search example: `http://127.0.0.1:8000/search?q=cançons%20tristes&limit=5`

### 3) Run frontend

From repository root:

```bash
python -m http.server 3000 -d app/frontend
```

Frontend URL:

- `http://127.0.0.1:3000`

Frontend API config file:

- [app/frontend/config.js](app/frontend/config.js)

## API contract (prototype)

`GET /search?q=<query>&limit=<n>` returns:

- `traditional_results[]`
- `intelligent_results[]`
- `map_points[]`

All values are test data for UI demonstration.

## Challenge alignment (summary)

This scaffold supports the stated challenge direction:

- modernized discovery UX for Viasona
- side-by-side traditional vs intelligent search output
- visual navigation through a song map
- clean separation between prototype environment and future real integration

## Next implementation phase (not yet implemented)

- real traditional search engine and typo-tolerance logic
- real semantic/LLM-assisted intelligent search
- embedding-based map coordinates and clustering
- Spotify preview and recommendation integration
- user validation experiments and metrics instrumentation

## YouTube pipeline note

The YouTube audio module remains available and unchanged. See:

- [youtube_audio_pipeline/README.md](youtube_audio_pipeline/README.md)

## Additional documentation

- [docs/local-development.md](docs/local-development.md)
- [app/frontend/README.md](app/frontend/README.md)
- [app/backend/README.md](app/backend/README.md)