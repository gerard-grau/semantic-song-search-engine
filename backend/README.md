# Backend

This folder contains the current FastAPI backend used for the MVP.

## Current purpose

The backend is mock-based for now. It provides stable API shapes for:

- classic search
- smart search
- song detail
- recommendations

Later, these handlers can be replaced with real logic connected to MariaDB, the classic search engine, and semantic retrieval components.

## Main files

- [api/main.py](api/main.py): FastAPI app entrypoint
- [api/routes/search.py](api/routes/search.py): search endpoints
- [api/routes/songs.py](api/routes/songs.py): song detail and recommendations
- [api/mock_data.py](api/mock_data.py): mock catalog and scoring logic
- [api/schemas.py](api/schemas.py): response models

## Local run

Run the application from the repository root using the FastAPI app object in `backend.api.main:app`.

Default local URL:

- `http://127.0.0.1:8000`

Interactive API docs:

- `http://127.0.0.1:8000/docs`

## Current endpoints

- `GET /`
- `GET /health`
- `GET /search/classic?q=amor impossible`
- `GET /search/smart?q=songs for a nostalgic night drive`
- `GET /songs/llum-dins-la-pluja`
- `GET /songs/llum-dins-la-pluja/recommendations`

## Notes

- CORS is configured for local frontend development on port `3000`.
- No database is required yet.
- All data is currently generated from mock content.
