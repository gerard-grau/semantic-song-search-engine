# Semantic Song Search Engine

Semantic search engine for Viasona-oriented musical content, developed for the Engineering Projects course.

## Current MVP status

The repository already includes a first stakeholder-facing MVP with:

- a polished frontend built with Next.js
- a mock backend API built with FastAPI
- mock search results for classic and smart search flows
- a song detail view with recommendations
- fallback frontend data when the backend is not running

## Project objectives

This project aims to modernize a large-scale song and lyrics search experience by combining a fast traditional search engine with a semantic search pipeline.

### Main goals

- Reduce response time of the traditional search flow to under 1 second.
- Support partial queries and tolerate spelling mistakes.
- Enable semantic search in natural language.
- Support discovery by mood, theme, and song similarity.
- Prepare the system for personalized recommendations and playlist generation.
- Build a maintainable data pipeline for transforming raw source data into application-ready datasets.
- Use MariaDB as the structured relational database for the application layer.

### Functional scope

The platform is planned as a hybrid search system with two complementary engines:

1. **Classic search engine**
	- Fast retrieval over structured song metadata and lyrics.
	- Typo tolerance using classical similarity techniques such as Levenshtein distance.
	- Partial matching and efficient indexing strategies.

2. **Smart search engine**
	- Semantic retrieval based on embeddings and nearest-neighbour style search.
	- Natural-language querying.
	- Similar-song recommendations and emotion-oriented discovery.

### Technical direction

- **ETL in Python** to extract, clean, transform, and load source data.
- **MariaDB** for structured storage and application queries.
- **Custom vector-search-oriented components** for semantic retrieval experiments.
- **PyTorch-based ML experiments** for embedding and similarity models.
- **Next.js frontend + Python backend integration** for the MVP experience.

### Expected outcomes

- A usable prototype integrated around the Viasona search use case.
- A reproducible repository structure for ETL, backend, ML, frontend, and testing.
- A baseline for evaluating latency, usability, and semantic retrieval quality.

## Repository structure

Main folders relevant to the current MVP:

- [backend](backend): FastAPI mock API
- [frontend](frontend): Next.js stakeholder-facing web app
- [docs](docs): project documentation
- [data](data): raw and processed datasets
- [etl](etl): future ETL pipeline code
- [ml](ml): future ML experimentation and model code
- [tests](tests): test placeholders and future validation suites

## Local development

### Prerequisites

Install these tools locally:

- Python 3.11+ or 3.12
- Node.js 20+
- npm 10+

Optional but recommended:

- a Python virtual environment
- VS Code with Python and TypeScript support

### 1. Clone the repository

Clone the project and move into the repository root.

### 2. Backend setup

From the repository root:

1. Create a virtual environment if you do not already have one.
2. Activate the virtual environment.
3. Install Python dependencies from [requirements.txt](requirements.txt).

The backend currently uses these packages:

- `fastapi`
- `uvicorn`
- `pydantic`

### 3. Frontend setup

From [frontend](frontend):

1. Install dependencies with npm.
2. Optionally create a local environment file from [frontend/.env.local.example](frontend/.env.local.example).

The frontend currently uses:

- `next`
- `react`
- `react-dom`
- `typescript`

## Running the app locally

You can run the MVP in two ways.

### Option A: frontend only

Run the Next.js app by itself.

What happens in this mode:

- the UI works
- the search pages still render
- the app uses built-in mock data from [frontend/lib/mock-data.ts](frontend/lib/mock-data.ts)
- no backend process is required

Use this if you only want to demo the interface.

### Option B: frontend + backend

Run both services locally.

#### Start the backend

Run the FastAPI app from the repository root using the application in [backend/api/main.py](backend/api/main.py).

Default backend URL:

- `http://127.0.0.1:8000`

Useful backend routes:

- `/`
- `/health`
- `/docs`
- `/search/classic?q=amor impossible`
- `/search/smart?q=songs for a nostalgic night drive`
- `/songs/llum-dins-la-pluja`
- `/songs/llum-dins-la-pluja/recommendations`

#### Start the frontend

Run the Next.js app from [frontend](frontend).

Default frontend URL:

- `http://127.0.0.1:3000`

When both apps are running:

- the frontend calls the backend through `NEXT_PUBLIC_API_BASE_URL`
- if the backend is unreachable, the frontend automatically falls back to local mock data

## Local environment variables

The frontend expects:

- `NEXT_PUBLIC_API_BASE_URL`

Recommended local value:

- `http://127.0.0.1:8000`

Reference example files:

- [frontend/.env.local.example](frontend/.env.local.example)
- [.env.example](.env.example)

For local frontend development, copy the frontend example file into `frontend/.env.local`.

## Available MVP pages

Once the frontend is running:

- Home page: `http://127.0.0.1:3000`
- Search demo: `http://127.0.0.1:3000/search`
- Song detail example: `http://127.0.0.1:3000/song/llum-dins-la-pluja`

## API overview

The current backend is intentionally mock-based. It is meant to preserve the API contract while the real engines are developed.

Implemented endpoints:

- `GET /health`: backend health check
- `GET /search/classic`: mock classic search results
- `GET /search/smart`: mock semantic search results
- `GET /songs/{song_id}`: mock song detail
- `GET /songs/{song_id}/recommendations`: mock related songs

Relevant backend files:

- [backend/api/main.py](backend/api/main.py)
- [backend/api/routes/search.py](backend/api/routes/search.py)
- [backend/api/routes/songs.py](backend/api/routes/songs.py)
- [backend/api/mock_data.py](backend/api/mock_data.py)
- [backend/api/schemas.py](backend/api/schemas.py)

## Frontend overview

The frontend is a Next.js App Router project.

Relevant frontend files:

- [frontend/app/layout.tsx](frontend/app/layout.tsx)
- [frontend/app/page.tsx](frontend/app/page.tsx)
- [frontend/app/search/page.tsx](frontend/app/search/page.tsx)
- [frontend/app/song/[id]/page.tsx](frontend/app/song/[id]/page.tsx)
- [frontend/app/globals.css](frontend/app/globals.css)
- [frontend/lib/api.ts](frontend/lib/api.ts)
- [frontend/lib/mock-data.ts](frontend/lib/mock-data.ts)

## Build validation

The frontend production build has already been validated successfully.

Recommended checks before sharing the demo locally:

- build the frontend
- open the home page
- open the search page
- open one song detail page
- optionally inspect the API docs page

## Troubleshooting

### The frontend starts but no backend results appear

This is expected if the backend is not running. The UI falls back to local mock data.

### The frontend cannot reach the backend

Check that:

- the backend is running on port `8000`
- the frontend environment variable points to the same URL
- CORS in [backend/api/main.py](backend/api/main.py) still allows `http://localhost:3000` and `http://127.0.0.1:3000`

### Python imports fail

Make sure the virtual environment is activated and dependencies from [requirements.txt](requirements.txt) are installed.

### Next.js imports or types fail

Make sure npm dependencies are installed inside [frontend](frontend).

## Additional documentation

- [docs/local-development.md](docs/local-development.md)
- [frontend/README.md](frontend/README.md)
- [backend/README.md](backend/README.md)