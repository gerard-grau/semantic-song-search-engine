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
