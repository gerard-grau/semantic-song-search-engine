# Local development guide

This document describes how to run the current **prototype scaffold**.

## Services

The prototype has two services:

1. frontend UI in [../app/frontend](../app/frontend)
2. backend API in [../app/backend](../app/backend)

The frontend layout can be shown with backend data or fallback mock data.

## Prerequisites

- Python 3.11+
- Optional virtual environment (`.venv`)
- `ffmpeg` only for [../youtube_audio_pipeline](../youtube_audio_pipeline)

## Setup

From repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run backend

From repository root:

```bash
uvicorn app.backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

Useful URLs:

- API root: `http://127.0.0.1:8000`
- health: `http://127.0.0.1:8000/health`
- docs: `http://127.0.0.1:8000/docs`
- search sample: `http://127.0.0.1:8000/search?q=cançons%20tristes&limit=5`

## Run frontend

From repository root:

```bash
python -m http.server 3000 -d app/frontend
```

Frontend URL:

- `http://127.0.0.1:3000`

API URL used by frontend:

- [../app/frontend/config.js](../app/frontend/config.js)

If needed, copy [../app/frontend/config.example.js](../app/frontend/config.example.js) to `app/frontend/config.js` and update `API_BASE_URL`.

## Current prototype behavior

- wide search bar at the top
- left side has:
  - traditional results list
  - intelligent results list
- right side has a map panel with placeholder points
- frontend requests `GET /search`
- if backend is down, frontend renders built-in fallback mock data

## Notebook setup (optional)

If you need notebooks in the same environment:

```bash
pip install -r requirements-notebooks.txt
python -m ipykernel install --user --name semantic-song-search --display-name "semantic-song-search (.venv)"
```

Then open notebooks from [../notebooks](../notebooks).

## Known limitations

- No real traditional search engine yet
- No real intelligent/ML ranking yet
- No real map clustering logic yet
- No production data integration yet

## Planned next phase

- replace mock search ranking with real classic engine
- integrate semantic retrieval and LLM query interpretation
- drive map points from embeddings/clusters
- add recommendation and Spotify preview integration
