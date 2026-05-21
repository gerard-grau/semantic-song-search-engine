# Backend Startup Performance — Research Notes

**Context:** the FastAPI backend takes 5–10 minutes to become ready after `uvicorn` is launched. This file is the working notebook for the investigation + planned fixes. Continued across sessions — append, don't overwrite.

Branch at time of investigation: `feature/qdrant-cercador`.
Date: 2026-05-21.

---

## 1. Measured cold-start timings (one process, sequential, WSL2 on `/mnt/c`)

| Phase | Time | Notes |
|---|---|---|
| `import` chain through `data_loader` (numpy/pandas/pyarrow + config) | **9.9 s** | Eager imports only |
| `load_visible_songs()` | **2.2 s** | reads `songs_meta.parquet` (60 MB, 85,743 rows) + `to_dict('records')` |
| `get_visible_index()` | **26.1 s** | reads `embedded_songs_top5000.parquet` (301 MB) and **string-parses 22,540 embedding cells** (4508 rows × 5 fields × 1024 floats) |
| `import` chain through `cercador_index` | 5.3 s | mostly already-loaded libs |
| `prewarm_cercador()` | **26.6 s** | wordfreq lexicon (50,594 words) + tokenises 78 K items; today this runs in background |
| `from transformers import …` (with torch + TF + Flax auto-import) | **47.2 s** | TF/Flax aren't used by us but transformers imports them anyway |
| `AutoModel.from_pretrained("BAAI/bge-m3")` from disk on `/mnt/c` | **244.5 s** | 2.3 GB safetensors over WSL2 9P bridge — this is the giant single item |
| first dummy `encode_query` (JIT) | 7.0 s | |
| second `encode_query` | 0.15 s | warmed |
| **Awaited total before serving** | **≈ 337 s ≈ 5.6 min** | matches user's reported 5–10 min |

Cercador `prewarm` (26.6 s) currently runs in background after the model load → not on the critical path, but only kicks off *after* model load finishes.

## 2. Why each phase is slow (root causes, not symptoms)

### Embeddings stored as JSON strings, not floats — `data_loader.load_embeddings_for_ids`
The parquet columns `embedded_lyrics`, `embedded_qualitative_description`, `embedded_title`, `embedded_album`, `embedded_artist` are arrow `string` columns. Each cell is a literal Python-style list:

```
type=str, length≈21,720 bytes
"[0.0019394776318222284,0.03692561015486717,-0.027220085…]"
```

Loader does `np.fromstring(cell.strip('[]'), sep=',')` per cell. Measured ≈ 2.0 s per field over 4508 rows × 5 fields = ~10 s of text→float, plus `to_pylist()` materialisation and Python-loop `np.stack` overhead on top. Total ~26 s. Recoverable: ~24 s by writing native `list<float32>` (or `fixed_size_list<float32, 1024>`).

### Model load 244 s — WSL `/mnt/c` is the limiter, not the model itself
`BAAI/bge-m3` is XLM-RoBERTa-large (568 M params, ~2.3 GB safetensors). WSL2's 9P bridge to NTFS reads at ~10–30 MB/s sustained — so 80–230 s pure read time alone, plus PyTorch state-dict copy. Confirmed cold from HF cache that already exists on the Windows drive.

### Transformers auto-imports TensorFlow + Flax
Stderr shows `cpu_feature_guard.cc` (TF) and `cudart_stub.cc` (Flax/JAX detection). We only use PyTorch. Set `TRANSFORMERS_NO_TF=1` and `TRANSFORMERS_NO_FLAX=1` *before* importing transformers and this disappears.

### Lifespan is awaited sequentially
`app/backend/api/main.py:93-104` — each `await loop.run_in_executor(...)` waits for the previous one. The visible-index build (CPU+disk) and the encoder load (mostly disk) are independent and could run via `asyncio.gather`. Cercador prewarm is the only one actually backgrounded today.

```python
await loop.run_in_executor(None, _safe_call, get_visible_index, "visible index")
await loop.run_in_executor(None, _safe_call, load_encoder, "embedding model")
await loop.run_in_executor(None, _safe_call, _warm_encoder, "encoder warm-up")
loop.run_in_executor(None, _safe_call, prewarm_cercador, "cercador index")  # bg only
```

### Cercador prewarm has duplicate work
`CercadorIndex.build` does `_index_songs/grups/noticies` which tokenises every title/artist/snippet, and then re-tokenises everything *again* to build `catalog_tokens`. Also `_load_grups`/`_load_noticies` use `df.iterrows()`.

## 3. Fixes ranked by wall-time saved

| # | Change | File(s) | Est. saving | Effort |
|---|---|---|---|---|
| 1 | **Move HuggingFace cache off `/mnt/c`** — `export HF_HOME=~/.cache/huggingface` (ext4) and pre-pull the model once | env / shell | **150–200 s** | trivial |
| 2 | Rewrite `embedded_songs_top5000.parquet` with native `list<float32>`; replace string parse in `load_embeddings_for_ids` with `column.flatten().to_numpy().reshape(N, D)` | `data_pipeline/step3_filter_top5000_embeddings.py`, `app/backend/core/data_loader.py` | ~24 s | medium (one-time rebuild) |
| 3 | `os.environ.setdefault("TRANSFORMERS_NO_TF","1"); setdefault("TRANSFORMERS_NO_FLAX","1")` *before* the transformers import path | top of `app/backend/api/main.py` (and `encoder.py`) | 5–10 s | trivial |
| 4 | Run `get_visible_index`, `load_encoder+warmup`, `prewarm_cercador` concurrently via `asyncio.gather` | `app/backend/api/main.py` lifespan | ~25 s | small |
| 5 | Move whole project off `/mnt/c` onto WSL ext4 (`~/dev/…`) | infra | another 10–30 s | one-time copy, breaks Windows-side editing |
| 6 | Replace `df.iterrows()` in `_load_grups`/`_load_noticies`; merge `catalog_tokens` into `_index_*` | `app/backend/core/cercador_index.py` | 5–10 s (background path only) | small |
| 7 | Skip `df.to_dict('records')` in `_read_meta_snapshot`; iterate Arrow columns | `app/backend/core/data_loader.py` | 0.5–1 s | small |
| 8 | (If quality permits) swap bge-m3 for a smaller multilingual encoder + rerun `preembedding.py` | `app/backend/core/encoder.py`, `ml/embeddings/preembedding.py` | 100–150 s | big (full re-embed) |

If we ship 1 + 3 + 4: ~5.6 min → ~1.5 min. Add 2: ~1 min. Add 5: ~30 s.

## 4. Hot path verification (do not break)

The `/api/filter` hot path that startup is pre-warming for:
1. `encode_query(text)` — one forward pass.
2. One matmul against `_visible_index["matrix"]` (N=4508, F=5, D=1024 float32 cube, L2-normalised).

Any change to embeddings parquet schema must preserve `EMBEDDING_FIELD_COLUMNS` order (lyrics, qualitative, title, album, artist) — see `app/backend/core/data_loader.py:77`. The dim must remain 1024 to match `encoder.MODEL_DIM`, or the filter falls back to word-overlap.

## 5. Files / lines touched by the plan

- `app/backend/api/main.py` — lifespan reorder, env-var guards.
- `app/backend/core/data_loader.py` — `load_embeddings_for_ids`, `_read_meta_snapshot`.
- `app/backend/core/cercador_index.py` — `_load_grups`, `_load_noticies`, merge catalog_tokens.
- `app/backend/core/encoder.py` — only if we want a smaller encoder.
- `data_pipeline/step3_filter_top5000_embeddings.py` — write native `list<float32>` columns.

## 6. Implementation order to attack next session

1. **Fix #1** (HF_HOME on ext4) — verify with `ls -la ~/.cache/huggingface` and re-run the timing harness in this file.
2. **Fix #3** (env vars) — measure transformers import drop.
3. **Fix #4** (parallel lifespan) — confirm with FastAPI startup log.
4. **Fix #2** (native parquet) — needs a one-time pipeline rerun; gate it behind `--force` so it doesn't break existing deployments.
5. Re-measure end-to-end and update Section 1 of this file.

## 7. Timing harness (reusable)

Drop this into a scratch script when re-measuring:

```python
import time

t0 = time.time(); from app.backend.core.data_loader import load_visible_songs, get_visible_index
print("data_loader import:", time.time()-t0)

t0 = time.time(); load_visible_songs()
print("load_visible_songs:", time.time()-t0)

t0 = time.time(); get_visible_index()
print("get_visible_index:", time.time()-t0)

t0 = time.time(); from app.backend.core.encoder import load_encoder, encode_query
print("encoder import:", time.time()-t0)

t0 = time.time(); load_encoder()
print("load_encoder:", time.time()-t0)

t0 = time.time(); encode_query("warmup")
print("first encode_query (warmup):", time.time()-t0)

t0 = time.time(); encode_query("alguna cosa")
print("second encode_query:", time.time()-t0)

t0 = time.time(); from app.backend.core.cercador_index import prewarm
print("cercador import:", time.time()-t0)

t0 = time.time(); prewarm()
print("cercador prewarm:", time.time()-t0)
```

## 8. Open questions for the user

- Are we willing to relocate the whole repo (or just the HF cache) off `/mnt/c`? Biggest single win.
- Is bge-m3 quality required, or would a smaller multilingual encoder (e.g. `multilingual-e5-small`) be acceptable? Would unlock another 100+ s.
- Is the qdrant work on the current branch (`feature/qdrant-cercador`) intended to replace the in-process matmul path? If so, prioritisation of #2 (native parquet) changes — qdrant has its own storage.

---

## Changelog (append per session)

- **2026-05-21 (session 1):** Initial measurements + plan written. No code changes yet.
