# Dev Notes — feature/qdrant-cercador

Changes made on this branch relative to `master`.

---

## How to run (full stack)

### 1. Start Qdrant

**Option A — native binary (recommended for local dev):**
```bash
cd ~/qdrant
./qdrant   # serves on localhost:6333, persists data in ./storage/
```
Snapshots for restore must live in `~/snapshots/` (relative to the dir you launch from).

**Option B — Docker:**
```bash
docker run -d --name qdrant_server \
    -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage \
    qdrant/qdrant
```
With the `-v` volume mount, data persists across restarts. Without it, data lives inside the container (use `docker cp` to extract snapshots).

### 2. Restore Qdrant collections from snapshots

The two collections (`songs_qualitative`, `songs_lyrics_chunks`) are not version-controlled — they must be restored from snapshots. See "Downloading snapshots from the server" below.

Once you have the `.snapshot` files in `~/snapshots/`:

```bash
# Restore qualitative collection (86k songs, ~400MB snapshot)
curl -X PUT "http://localhost:6333/collections/songs_qualitative/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d '{"location": "file:///home/miquel/snapshots/songs_qualitative-<name>.snapshot"}'

# Restore lyrics-chunks collection (~780k chunks, ~3GB snapshot)
curl -X PUT "http://localhost:6333/collections/songs_lyrics_chunks/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d '{"location": "file:///home/miquel/snapshots/songs_lyrics_chunks-<name>.snapshot"}'
```

Verify both collections exist:
```bash
curl "http://localhost:6333/collections"
```

### 3. Start the backend

```bash
cd /home/miquel/Universitat/PE/semantic-song-search-engine
source .venv/bin/activate
CUDA_VISIBLE_DEVICES="" python3 -m uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

`CUDA_VISIBLE_DEVICES=""` forces CPU inference (avoids GPU OOM on the local 6GB card).

The first lyrics query after startup will:
1. Load the cross-encoder model (`~120MB`, downloads automatically on first call)
2. Run a slow first inference (~2-3s)

Subsequent queries: ~500ms–1s (cross-encoder on 100 pairs, CPU).

### 4. Start the frontend

```bash
cd app/frontend
npm install
npm run dev   # http://localhost:3000
```

---

## Downloading Qdrant snapshots from the GPU server

The lyrics collection was indexed on `pe@aulagpus.fib.upc.edu` (GPU server). To transfer a fresh snapshot:

**On the server:**
```bash
# Create snapshot
curl -X POST "http://localhost:6333/collections/songs_lyrics_chunks/snapshots"
# → returns { "name": "songs_lyrics_chunks-<timestamp>.snapshot" }

# If running Docker, extract from container:
docker cp qdrant_server:/qdrant/snapshots/songs_lyrics_chunks/ ~/lyrics_snapshot/
sudo chown pe:pe ~/lyrics_snapshot/*.snapshot   # Docker creates root-owned files
```

**On your local machine:**
```bash
mkdir -p ~/snapshots
scp pe@aulagpus.fib.upc.edu:~/lyrics_snapshot/songs_lyrics_chunks-*.snapshot ~/snapshots/
```

The qualitative collection (`songs_qualitative`) can be re-indexed locally in minutes from the existing parquets — no need to transfer from the server:
```bash
python3 -m ml.embeddings.index_qdrant_docker --only-qualitative
```

---

## What's on this branch

### 1. Qdrant backend: Docker → native binary

Qdrant runs as a standalone process on `localhost:6333`. The client in `app/backend/core/qdrant_search.py` connects over TCP and gracefully falls back to the matrix approach if Qdrant is unreachable (retries every 30s to avoid hammering on every keystroke).

**Key files:**
- `app/backend/core/qdrant_search.py` — new module
- `requirements.txt` — added `qdrant-client>=1.9,<2.0`, `sentence-transformers>=3.0,<4.0`

---

### 2. Qdrant collections

**`songs_qualitative`** — one point per song, `embedded_qualitative_description` vector. Good for mood/theme queries. Indexed from existing parquets (no re-embedding needed).

**`songs_lyrics_chunks`** — one point per **40-word chunk** (20-word overlap, ≥8 words to keep), lowercased. Good for lyric-content queries. Indexed from `augmented_songs.csv` (re-embeds all lyrics with BGE-M3). ~780k chunks from ~86k songs.

Chunk size changed from 100/50 to **40/20** to reduce embedding dilution: shorter chunks let the cross-encoder see specific phrases more clearly.

**Indexing script:** `ml/embeddings/index_qdrant_docker.py`

```bash
# Qualitative (fast — reuses parquets, run locally):
python3 -m ml.embeddings.index_qdrant_docker --only-qualitative

# Lyrics chunks (slow — run on GPU server):
python3 -m ml.embeddings.index_qdrant_docker --only-lyrics
python3 -m ml.embeddings.index_qdrant_docker --only-lyrics --resume   # resume after crash
```

---

### 3. Hybrid lyrics search with cross-encoder reranking

**File:** `app/backend/core/qdrant_search.py` → `search_lyrics_chunks()`

Pipeline when `query_text` is provided:

1. **Dense search** — threshold=0.0, fetch top-200 chunks (brute-force cosine, exact). Threshold is dropped so synonym queries (cosine ~0.15–0.25) aren't filtered before the reranker sees them.
2. **Dedup** — best-scoring chunk per song → ~80–120 unique songs.
3. **Keyword-filtered dense search** — `MatchText` AND filter for meaningful tokens (≥3 chars, non-stopword), ranked by cosine. Catches verbatim phrases that dense search undershoots.
4. **RRF fusion** — asymmetric: exact multi-word keyword match gets k=6 (strong), single-word fallback k=51 (weak). Pool capped at 100 candidates.
5. **Cross-encoder reranking** — `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` scores each `(query, chunk_text)` pair jointly. Handles synonyms the bi-encoder misses. Scores normalised via sigmoid → [0, 1].
6. **Dedup by (artist, title)** → return top-`limit`.

---

### 4. Cercador suggestions — Qdrant path

**File:** `app/backend/api/routes/cercador.py`

`/api/cercador/suggestions` tries Qdrant first, falls back to matrix.

| Mode | Sugerències slot | Lletres slot |
|---|---|---|
| `all` (Combinat) | qualitative results | lyrics results |
| `qualitative` (Temàtica) | qualitative results | — |
| `lyrics` (Literal) | lyrics results (CE reranked) | — |
| `matrix` | matrix top-5000 | matrix top-5000 |

Limit raised from 5 to **10** for all suggestion slots.

---

### 5. Artist filter

Each artist row has a "Filtrar" button. Active filter shown as a chip; all suggestion calls are narrowed to that artist via Qdrant payload filter (`MatchAny` over name variants).

---

### 6. Mode selector UI

Replaced 4 pill buttons with a **3-position segmented control** (iOS-style):

```
[ Temàtica | Combinat | Literal ]   [Matriu]
```

- **Temàtica** / **Combinat** / **Literal** — main slider (qualitative ↔ both ↔ lyrics)
- **Matriu** — secondary dev button (bypasses Qdrant, uses top-5000 matrix)

---

### 7. Misc fixes

- `qdrant-client 1.18` breaking change: `.search()` removed → migrated to `.query_points()` (returns `.points` attribute).
- `SearchParams(exact=True)` on all Qdrant calls → deterministic results (HNSW is non-deterministic without this).
- Full-text index created on `chunk_text_snippet` at first connection (idempotent).
- `data_loader.py` / `data_pipeline.py`: bytes/latin-1 encoding edge cases.
- `encoder.py`: force CPU with `CUDA_VISIBLE_DEVICES=""` on WSL.
