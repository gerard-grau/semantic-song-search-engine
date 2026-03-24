# Local development guide

This document explains how to work with the current MVP locally.

## Services

The MVP is split into two parts:

1. a Next.js frontend in [../frontend](../frontend)
2. a FastAPI backend in [../backend](../backend)

The frontend can run with or without the backend.

## Recommended workflow

### Frontend-only demo mode

Use this when you only need the interface for meetings, screenshots, or stakeholder demos.

Behavior:

- the frontend starts normally
- pages render using built-in mock data
- no Python process is required

### Full local MVP mode

Use this when you want the frontend to consume the mock backend API.

Behavior:

- the backend serves JSON responses
- the frontend fetches data from the API
- the frontend still has a fallback if the backend stops responding

## Frontend setup

From [../frontend](../frontend):

- install dependencies
- create `frontend/.env.local` from [../frontend/.env.local.example](../frontend/.env.local.example)
- start the development server

Default frontend URL:

- `http://127.0.0.1:3000`

## Backend setup

From the repository root:

- create and activate a Python virtual environment
- install dependencies from [../requirements.txt](../requirements.txt)
- start the FastAPI application from `backend.api.main:app`

System dependencies for the YouTube pipeline:

- `aria2`
- `ffmpeg`

## Notebook setup (same environment)

Use the same root `.venv` unless dependency conflicts appear.

From the repository root:

- install base backend deps from [../requirements.txt](../requirements.txt)
- install notebook deps from [../requirements-notebooks.txt](../requirements-notebooks.txt)
- register `.venv` as a Jupyter kernel

Suggested kernel name:

- `semantic-song-search (.venv)`

Then open notebooks from [../notebooks](../notebooks) and select that kernel.

Example commands:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-notebooks.txt
python -m ipykernel install --user --name semantic-song-search --display-name "semantic-song-search (.venv)"
```

Default backend URL:

- `http://127.0.0.1:8000`

API docs:

- `http://127.0.0.1:8000/docs`

## Frontend environment variable

Expected variable:

- `NEXT_PUBLIC_API_BASE_URL`

Expected value for local development:

- `http://127.0.0.1:8000`

## Useful pages

- home: `http://127.0.0.1:3000`
- search demo: `http://127.0.0.1:3000/search`
- song detail demo: `http://127.0.0.1:3000/song/llum-dins-la-pluja`

## Useful API routes

- `GET /health`
- `GET /search/classic?q=amor impossible`
- `GET /search/smart?q=songs for a nostalgic night drive`
- `GET /songs/llum-dins-la-pluja`
- `GET /songs/llum-dins-la-pluja/recommendations`

## YouTube pipeline usage

Prepare URL list:

- edit [../youtube_audio_pipeline/urls.example.txt](../youtube_audio_pipeline/urls.example.txt)

Run from repository root:

```bash
python -m youtube_audio_pipeline.main --urls-file youtube_audio_pipeline/urls.example.txt
```

Common tuning options:

```bash
python -m youtube_audio_pipeline.main \
	--urls-file youtube_audio_pipeline/urls.example.txt \
	--output-csv data/processed/my_youtube_features.csv \
	--workers 22 \
	--flush-every 250
```

Default output:

- `data/processed/youtube_song_characteristics.csv`

### Benchmark on deployment server

Run tuning benchmarks on the same machine where you will process large batches.

```bash
python -m youtube_audio_pipeline.benchmark \
	--urls-file youtube_audio_pipeline/urls.benchmark.example.txt \
	--max-urls 10 \
	--workers-list 1,2,4,8,12,16,22 \
	--repeats 1
```

Benchmark summary CSV:

- `data/processed/youtube_pipeline_benchmark.csv`

Pick the worker count with the highest `urls_per_second` while keeping `success_rate` near `1.0`.

## Current limitations

- no MariaDB connection yet
- no real ETL ingestion yet
- no production search index yet
- smart search is mock-scored, not model-based yet
- recommendations are mock-generated

## Next implementation targets

- connect backend services to MariaDB
- implement the real classic search engine
- define API service boundaries for smart search
- replace mock catalog data with real records
- add tests for API contracts and UI flows
