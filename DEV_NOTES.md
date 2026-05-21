# Dev Notes — feature/qdrant-cercador

Changes made on this branch relative to `master`.

---

## How to run (full stack)

### 1. Start Qdrant

**Option A — native binary (recommended for local dev):**
```bash
cd ~
~/qdrant/qdrant   # serves on localhost:6333, persists data in ~/storage/
```
Launching from `~` means Qdrant's snapshots directory is `~/snapshots/` and its
storage directory is `~/storage/`. The restore commands below assume this layout.

**Option B — Docker:**
```bash
docker run -d --name qdrant_server \
    -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage \
    qdrant/qdrant
```
With `-v`, data persists across restarts. Without it, collections live only inside
the container (use `docker cp` to extract snapshots before stopping).

---

### 2. Get the Qdrant collections

Two collections are needed: `songs_qualitative` and `songs_lyrics_chunks`.

#### `songs_lyrics_chunks` — download snapshot from the GPU server

This collection (~780k chunks, ~3 GB snapshot) was indexed on the GPU server and
is too slow to re-embed locally. Transfer the snapshot:

**On the GPU server** (`pe@aulagpus.fib.upc.edu`):
```bash
# Create a fresh snapshot (skip if one already exists)
curl -X POST "http://localhost:6333/collections/songs_lyrics_chunks/snapshots"
# → returns { "name": "songs_lyrics_chunks-<timestamp>.snapshot" }

# If running Docker, copy out of the container first:
docker cp qdrant_server:/qdrant/snapshots/songs_lyrics_chunks/ ~/lyrics_snapshot/
sudo chown pe:pe ~/lyrics_snapshot/*.snapshot   # Docker creates root-owned files
```

**On your local machine:**
```bash
mkdir -p ~/snapshots
scp -P 60054 pe@aulagpus.fib.upc.edu:~/lyrics_snapshot/songs_lyrics_chunks-*.snapshot ~/snapshots/
```

#### `songs_qualitative` — re-index locally (fast, no GPU)

This collection (86k songs, ~400 MB) is indexed from the pre-computed parquets in
`ml/embeddings/embedded_songs_dataset/`. No re-embedding — takes ~2 min on CPU:

```bash
source .venv/bin/activate
CUDA_VISIBLE_DEVICES="" python3 -m ml.embeddings.index_qdrant_docker --only-qualitative
```

> **Note:** After the Títol mode was added, `songs_qualitative` now stores two
> named vectors per song (`embedded_qualitative_description` + `embedded_title`).
> Always use the script above — old snapshots of this collection will not work.

---

### 3. Restore `songs_lyrics_chunks` from snapshot

Once the `.snapshot` file is in `~/snapshots/` (and Qdrant is running from `~`):

```bash
# Replace <name> with the actual filename (tab-complete works)
curl -X PUT "http://localhost:6333/collections/songs_lyrics_chunks/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d '{"location": "file:///home/<your_user>/snapshots/songs_lyrics_chunks-<name>.snapshot"}'
```

Verify both collections are present:
```bash
curl -s "http://localhost:6333/collections" | python3 -m json.tool
```

---

### 4. Start the backend

```bash
cd /path/to/semantic-song-search-engine
source .venv/bin/activate
CUDA_VISIBLE_DEVICES="" python3 -m uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

`CUDA_VISIBLE_DEVICES=""` forces CPU inference (avoids GPU OOM on a 6 GB card).

On first startup after a fresh clone, the cross-encoder model
(`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, ~120 MB) downloads automatically.
The first Lletra query will be slow (~2–3 s); subsequent ones ~500 ms–1 s.

---

### 5. Start the frontend

```bash
cd app/frontend
npm install
npm run dev   # http://localhost:3000
```

---

## Rebuilding everything from scratch (no snapshots)

If you have the pre-computed parquets in `ml/embeddings/embedded_songs_dataset/`
and `augmented_songs.csv` in `app/backend/data/raw/`, you can rebuild both
collections without downloading any snapshot.

```bash
source .venv/bin/activate

# 1. Qualitative + title collection (fast — reads existing parquets, no GPU)
CUDA_VISIBLE_DEVICES="" python3 -m ml.embeddings.index_qdrant_docker --only-qualitative

# 2. Lyrics-chunks collection (slow — re-embeds all lyrics with BGE-M3)
#    Run this on the GPU server, then transfer the snapshot as described above.
#    On a machine with a GPU:
python3 -m ml.embeddings.index_qdrant_docker --only-lyrics
#    If it crashes mid-way, resume from last checkpoint:
python3 -m ml.embeddings.index_qdrant_docker --only-lyrics --resume
```

After indexing lyrics on the GPU server, export and transfer the snapshot:
```bash
# On GPU server — create snapshot
curl -X POST "http://localhost:6333/collections/songs_lyrics_chunks/snapshots"
docker cp qdrant_server:/qdrant/snapshots/songs_lyrics_chunks/ ~/lyrics_snapshot/
sudo chown pe:pe ~/lyrics_snapshot/*.snapshot

# On your local machine
scp -P 60054 pe@aulagpus.fib.upc.edu:~/lyrics_snapshot/songs_lyrics_chunks-*.snapshot ~/snapshots/

# Restore locally
curl -X PUT "http://localhost:6333/collections/songs_lyrics_chunks/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d '{"location": "file:///home/<your_user>/snapshots/songs_lyrics_chunks-<name>.snapshot"}'
```

---

## What's on this branch

### 1. Qdrant backend

Qdrant runs as a standalone process on `localhost:6333`. The client in
`app/backend/core/qdrant_search.py` connects over TCP and gracefully falls back
to the matrix approach if Qdrant is unreachable (retries every 30 s).

**Key files:**
- `app/backend/core/qdrant_search.py` — Qdrant search module
- `requirements.txt` — added `qdrant-client>=1.9,<2.0`, `sentence-transformers>=3.0,<4.0`

---

### 2. Qdrant collections

**`songs_qualitative`** — one point per song, two named vectors:
- `embedded_qualitative_description` — mood/theme queries (Temàtica mode)
- `embedded_title` — title-similarity queries (Títol mode)

Indexed from the existing parquets; no re-embedding needed.

**`songs_lyrics_chunks`** — one point per **40-word chunk** (20-word overlap,
≥8 words to keep), lowercased. ~780k chunks from ~86k songs. Indexed from
`augmented_songs.csv` (re-embeds all lyrics with BGE-M3 — GPU server only).

---

### 3. Hybrid lyrics search with cross-encoder reranking

**File:** `app/backend/core/qdrant_search.py` → `search_lyrics_chunks()`

Pipeline for Lletra mode:

1. **Dense search** — threshold=0.0, fetch top-200 chunks (exact cosine). Threshold dropped so synonym queries (cosine ~0.15–0.25) aren't filtered before reranking.
2. **Dedup** — best chunk per song → ~80–120 unique songs.
3. **Keyword-filtered dense search** — `MatchText` AND filter (≥3-char non-stopword tokens), ranked by cosine. Catches verbatim phrases dense search misses.
4. **RRF fusion** — asymmetric: full AND match k=6 (strong), single-word fallback k=51 (weak). Pool capped at 100.
5. **Cross-encoder reranking** — `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` scores each `(query, chunk)` pair jointly. Sigmoid-normalised → [0, 1].
6. **Dedup by (artist, title)** → top-`limit`.

---

### 4. Cercador Suggerències — 3 modes

**File:** `app/backend/api/routes/cercador.py`

`/api/cercador/suggestions` tries Qdrant first, falls back to the matrix
(top-5000 visible songs) if Qdrant is unreachable.

| Mode | Suggerències slot | Lletres slot |
|---|---|---|
| `qualitative` (Temàtica) | qualitative-description results | — |
| `lyrics` (Lletra) | lyrics chunks, CE reranked | — |
| `title` (Títol) | title-embedding results | — |

Limit: **7** results per slot. Títol mode ignores the `exclude_ids` list so
exact title matches always surface even when the lexical engine already found
them in the Lletres column.

---

### 5. Artist filter

Each Grups row has a **Filtrar** button. Active filter shown as a chip; all
Qdrant calls are narrowed to that artist via a payload filter (`MatchAny` over
name variants). Grups display capped at 5 results.

---

### 6. Mode selector UI

3-position segmented control (iOS-style):

```
[ Temàtica | Lletra | Títol ]
```

Default is **Temàtica**. No more "Combinat" or "Matriu" developer buttons.

---

### 7. Misc fixes

- `qdrant-client 1.18` breaking change: `.search()` removed → migrated to `.query_points()`.
- `SearchParams(exact=True)` on all Qdrant calls → deterministic results.
- Full-text index on `chunk_text_snippet` created at first connection (idempotent).
- `encoder.py`: force CPU with `CUDA_VISIBLE_DEVICES=""` on WSL.
