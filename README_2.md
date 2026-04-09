# Semantic Song Search Engine

A prototype search experience built for **Viasona**, a Catalan music platform. The goal is to let users find songs by meaning — not just keywords — while also exposing traditional search results and a visual map of the song catalogue side by side.


---

## What this project does

### 1. Semantic (intelligent) search over song lyrics

The core idea is meaning-based retrieval. A user can type a query like _"cançons tristes sobre el mar"_ (sad songs about the sea) or even _"songs about resistance and youth"_ in any language, and the engine returns the most semantically similar songs from the catalogue.

This works via **`intfloat/multilingual-e5-large`**, a 1024-dimensional multilingual sentence embedding model. Each song's title, artist, and lyrics are encoded into a vector. At query time the query is also embedded (with a `query:` prefix) and cosine similarity is used to rank results. The notebook in `notebooks/` demonstrates this working end-to-end on Catalan songs from Oques Grasses and classic Catalan repertoire.

### 2. Traditional (keyword) search

Alongside the semantic results, the UI shows a conventional ranked list — intended for users who know exactly what they are looking for. Both lists are served from the same `GET /search` endpoint.

### 3. Visual song map

A right-side panel renders songs as positioned dots on a canvas. The intended final behavior is to place each song at 2D coordinates derived from its embedding (e.g. via UMAP/PCA projection), turning the map into a navigable space where similar songs cluster together.

### 4. YouTube audio feature pipeline

A standalone pipeline that:
- accepts a list of YouTube URLs (from a file or CLI args)
- downloads audio to a RAM disk (`/dev/shm`) using `yt-dlp` to avoid disk I/O
- converts audio to mono WAV with `ffmpeg`
- extracts **BPM**, **musical key**, and **loudness** using `essentia`
- writes results to a CSV at `data/processed/youtube_song_characteristics.csv`
- processes URLs in parallel (configurable worker count, up to CPU count)
- deduplicates by YouTube video ID and flushes to disk incrementally

This is the data collection layer that would feed the search engine with real audio features.

---

## Architecture overview

```
User browser
    │
    ▼
app/frontend/          ← Static HTML/CSS/JS, served with Python's http.server
    │  GET /search?q=...&limit=N
    ▼
app/backend/           ← FastAPI service (uvicorn)
    │  currently returns deterministic mock data
    │  future: real traditional engine + semantic embedding lookup
    ▼
data/processed/        ← CSV of audio features from the YouTube pipeline

notebooks/             ← Proof-of-concept: multilingual-e5-large semantic search
                          working over Catalan lyrics (runs standalone in Colab/Jupyter)

youtube_audio_pipeline/ ← Parallel downloader + Essentia feature extractor
```

---

## Components

| Path | What it is |
|---|---|
| `app/frontend/` | Static web app (Catalan UI). Search form, two result lists, map canvas. Falls back to inline mock data when backend is offline. |
| `app/backend/` | FastAPI app. One endpoint: `GET /search` returning `traditional_results`, `intelligent_results`, and `map_points`. No database yet — all mock. |
| `youtube_audio_pipeline/` | CLI pipeline. `python -m youtube_audio_pipeline --urls-file urls.txt --output-csv out.csv` |
| `notebooks/` | Jupyter notebooks showing `multilingual-e5-large` semantic search working on real Catalan song data. |
| `ml/` | Placeholder for future embedding model wrappers and training code. |
| `etl/` | Placeholder for future data ingestion from Viasona. |
| `data/` | `raw/` and `processed/` storage, gitignored content. |
| `tests/` | Placeholder test suites for classic search, smart search, and performance. |

---

## API

```
GET /search?q=<query>&limit=<n>
```

Response shape:

```json
{
  "query": "cançons tristes",
  "traditional_results": [{ "title": "...", "artist": "...", "score": 0.0 }],
  "intelligent_results": [{ "title": "...", "artist": "...", "score": 0.0 }],
  "map_points": [{ "x": 0.0, "y": 0.0, "title": "..." }]
}
```

All values are currently mock. The schema is stable and the frontend consumes it directly.

---

## Quick start

**Requirements:** Python 3.11+, `ffmpeg` and `aria2` only for the audio pipeline.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Terminal 1 — backend
uvicorn app.backend.api.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — frontend
python -m http.server 3000 -d app/frontend
```

Open `http://127.0.0.1:3000`.

**Run the YouTube audio pipeline:**

```bash
python -m youtube_audio_pipeline --urls-file youtube_audio_pipeline/urls.example.txt
```

**Run the semantic search notebook:**

Open `notebooks/Catalan_Lyric_Semantic_Search_E5.ipynb` in Jupyter or Google Colab.

---

## What is not implemented yet

- Real traditional search engine (BM25, typo tolerance)
- Real semantic search integrated into the backend (the notebook shows it works; it just needs to be wired up)
- Embedding-based 2D map coordinates (UMAP/PCA projection)
- Actual Viasona song database ingestion (ETL)
- Spotify preview and recommendation integration
- Metrics and A/B testing instrumentation
