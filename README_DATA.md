# Data Update Guide

How to (re)generate the derived data files. Assumes the irreplaceable inputs
are already present at `app/backend/data/`:

```
embedded_songs.parquet      4.9 GB   ← song embeddings (5 fields × 1024-dim each)
augmented_songs.csv         115 MB   ← cleaned lyrics + metadata
cancons.csv                  87 MB   ← raw song metadata from Viasona
noticies.csv                 14 MB   ← used by the cercador
grups.csv                   2.2 MB   ← used by the cercador
```

Everything else (`embedded_songs_genres.parquet`, `embedded_songs_2d.parquet`,
`songs_meta.parquet`) is regenerable from those in a few minutes.

---

## Quick start

From the project root with the venv set up:

```bash
# 1. Genre classification
#    ~1.5 min. First run downloads intfloat/multilingual-e5-large (~2.2 GB)
#    to ~/.cache/huggingface/hub/.
.venv/bin/python -m ml.embeddings.classify_genres

# 2. 2-D projection + metadata snapshot
#    ~2-3 min on CPU. Reads the genres parquet written by step 1.
.venv/bin/python -m app.backend.core.data_pipeline \
    --limit 5000 \
    --method umap \
    --genre-mode soft \
    --alpha-genre 2.0

# 3. Restart the backend so it picks up the new songs_meta.parquet
#    (data_loader caches the snapshot in process memory.)
.venv/bin/uvicorn app.backend.main:app --reload
```

Then hard-refresh the frontend (Ctrl+Shift+R) if it's running.

---

## What each step writes

| Step | Output file | Contents |
|------|-------------|----------|
| 1 | `embedded_songs_genres.parquet` | `id_lyrics`, `genre` (slug), `genre_scores` (8-dim softmax profile) |
| 2 | `embedded_songs_2d.parquet` | `id_lyrics`, `x`, `y` — UMAP coords for the global scatter |
| 2 | `songs_meta.parquet` | Cleaned per-song metadata with `genre` joined in — what the API loads at startup |

---

## Common tunings

### Rebalance the genre distribution

The default zero-shot classifier under-represents rock (its label vector
collides with punk in E5 space). Pass `--prior` with per-genre mean-probability
targets to fix it. Anchor each weight near the value printed under
*"Raw distribution (pre-calibration)"* in the log; nudge only the genres
you want to move:

```bash
.venv/bin/python -m ml.embeddings.classify_genres \
    --prior "cançó-autor=0.155,pop=0.145,punk=0.10,rumba=0.123,hip-hop=0.122,electronica=0.111,folk=0.106,rock=0.14"
```

This particular setting shifts rock from ~0.3% to ~17% argmax rate and pulls
punk down from ~20% to ~3% — most other genres stay near their empirical
distribution. Re-run step 2 after.

Built-in presets: `--prior catalan`, `--prior uniform`, `--prior none`.

### Change cluster tightness in the 2-D map

`--alpha-genre` is how much the genre block dominates the projection:

| α   | genre share of squared distance |
|----:|--------------------------------:|
| 0   | 0% (no genre signal)            |
| 0.7 | 33%                             |
| 1.0 | 50%                             |
| 2.0 | 80% *(default)*                 |
| 3.0 | 90%                             |

Higher → tighter, more "cornered" clusters. Lower → softer, more organic shape.

### Other flags

- `--genre-mode soft|onehot|none` — soft softmax profile, hard argmax one-hot,
  or disable augmentation entirely.
- `--method umap|tsne|pca_umap` — projection algorithm.
- `--limit N` — number of songs to project (default `5000`, matches
  `VISIBLE_SONG_LIMIT` in `data_loader.py`).
- `--skip-meta` — skip rebuilding `songs_meta.parquet` (use when only the
  projection changed and genre data is unchanged).
- `--only-meta` — only rebuild `songs_meta.parquet` (use after editing labels
  if the 2-D layout doesn't need to move).

---

## Verifying it worked

```bash
.venv/bin/python - <<'PY'
import pyarrow.parquet as pq
for name in ("embedded_songs_2d", "songs_meta", "embedded_songs_genres"):
    t = pq.read_table(f"app/backend/data/{name}.parquet")
    print(f"{name:30s} rows={t.num_rows}")
df = pq.read_table("app/backend/data/songs_meta.parquet", columns=["genre"]).to_pandas()
print("\nGenre distribution in snapshot:")
print(df["genre"].value_counts().to_string())
PY
```

If every row has empty `genre`, step 1 didn't run before step 2 — re-run in
order.

---

## Troubleshooting

- **e5-large download stalls.** The first classify_genres call pulls
  ~2.2 GB from Hugging Face. Check `~/.cache/huggingface/hub/models--intfloat--multilingual-e5-large/`
  to see partial progress. On a slow link this can take 10+ minutes.
- **`embedded_songs.parquet not found`.** This file isn't in git — you need
  to copy it from the source machine (4.9 GB) before any step.
- **Backend still shows old genres after pipeline finishes.** Restart
  uvicorn. `data_loader._all_metadata_cache` is in-process memory; it
  only re-reads the snapshot on cold start.
- **Vite frontend doesn't pick up `genreColors.js` changes.** WSL2 file
  watching is unreliable on `/mnt/c` paths. Restart `npm run dev` and
  hard-refresh.
