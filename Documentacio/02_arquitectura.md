# 02 — Arquitectura

## Capes lògiques

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Frontend (React, port 5173)                                             │
│  ─────────────────────────────────────────────────────────────────────   │
│  WelcomePage ─▶ App / CercadorPage                                       │
│   App                                                                    │
│   ├── FilterBar     (chips de queries acumulades)                        │
│   ├── TopResults    (cançons actives ordenades per score)                │
│   ├── VizSelector   (2D | 3D | Navegació)                                │
│   ├── Scatter2D / Scatter3D / Navigation2D                               │
│   └── SongDetail    (modal de detall)                                    │
└──────────────────────────────────────────────────────────────────────────┘
                  │ axios (vite proxy /api → 127.0.0.1:8000)
                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Backend FastAPI (port 8000)                                             │
│  ─────────────────────────────────────────────────────────────────────   │
│  api/main.py            (lifespan precarrega encoder)                    │
│  api/routes/search.py   (/api/songs, /api/filter, /api/neighbors,        │
│                          /api/songs/{id})                                │
│  api/routes/cercador.py (/api/cercador?q=...)                            │
└──────────────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  core/                                                                   │
│  ─────────────────────────────────────────────────────────────────────   │
│  data_loader     (parquet + CSV → list[dict] amb embeddings)             │
│  encoder         (HuggingFace transformers, mean-pooling, L2 norm)       │
│  embeddings      (filter_embeddings, build_neighborhood, knn)            │
│  projections     (t-SNE 2D/3D, MDS local amb rotació de Procrustes)      │
│  similarity      (helpers vectorials compartits — l2/cosine)             │
└──────────────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Dades (offline)                                                         │
│  embedded_songs.parquet · augmented_songs.csv · cancons.csv ·            │
│  noticies.csv · grups.csv · embedded_songs_2d.parquet (opcional)         │
└──────────────────────────────────────────────────────────────────────────┘
```

## Contractes entre capes

### Frontend ↔ Backend

Tot el contracte està als models Pydantic d'`app/backend/api/schemas.py`.
El frontend mai inventa camps, sempre llegeix els que defineix l'esquema.

| Model | Camps clau |
| --- | --- |
| `SongResult` | `id`, `title`, `artist`, `album`, `genre`, `year`, `lyrics_snippet`, `score` |
| `SongDetail` | tots els de `SongResult` (sense `score`) + `full_lyrics`, `url`, `duration`, `language` |
| `Point2D` | `id`, `x`, `y`, `title`, `artist`, `genre`, `role` |
| `Point3D` | `Point2D` + `z` |
| `FilterRequest` | `query: str`, `song_ids: list[int] | None` |
| `NeighborsRequest` | `song_id`, `n=20`, `song_ids?`, `previous_song_id?`, `bridge_song_ids[]`, `bridge_count=5`, `previous_positions[]` |

### Backend ↔ core

Les rutes només cridenfuncions públiques de `core/`:

```
data_loader.load_all_songs() → list[dict]
data_loader.get_song_by_id(id) → dict | None
data_loader.get_songs_by_ids(ids) → list[dict]

embeddings.filter_embeddings(query, songs) → list[dict] (amb 'score')
embeddings.build_neighborhood(focal_id, all_songs, n, previous_song_id, bridge_song_ids, bridge_count) → list[dict]

projections.compute_tsne_2d(songs) → list[dict]
projections.compute_tsne_3d(songs) → list[dict]
projections.compute_neighborhood_2d(songs, focal_id, previous_song_id, previous_positions) → list[dict]
projections.get_all_projections_2d() → list[dict]
projections.get_all_projections_3d() → list[dict]
```

### core/ internament

```
encoder.encode_query(text) ──▶ vector L2-normalitzat (384-d)
encoder.encode_passages(texts, batch_size) ──▶ list[vector]

similarity.l2_normalize_matrix(M) ──▶ M_normed
similarity.l2_normalize_vector(v) ──▶ v_normed
similarity.cosine_matrix(M)       ──▶ M_normed @ M_normed.T (clip [-1,1])
similarity.cosine_vector(q, M)    ──▶ M_normed @ q_normed (clip [-1,1])
```

`similarity.py` és el punt únic on es fa la normalització L2 i el càlcul de
cosinus dens. Tant `embeddings.filter_embeddings`, `embeddings.get_nearest_neighbors`
com el muntatge de matrius de distància a `projections.compute_neighborhood_2d`
hi deleguen.

## Cicle de vida

1. **Arrencada de FastAPI**: el `lifespan` precarrega `encoder.load_encoder()`
   en un executor (60-90 s la primera vegada per descarregar i carregar el
   model). Sense aquest pas, la primera crida a `/api/filter` superaria el
   timeout del client.
2. **Primera crida a `/api/songs`**: `data_loader._load_from_real_data()` llegeix
   el parquet d'embeddings, el `augmented_songs.csv` (per chunks) i `cancons.csv`.
   Cau a `mock_songs.json` si alguna cosa falla. Resultat: `_songs_cache`.
3. **Projeccions completes**: `get_all_projections_2d()` intenta llegir
   `embedded_songs_2d.parquet`; si no existeix, calcula t-SNE 2D al moment i el
   guarda al cache (`_cached_all_2d`). `get_all_projections_3d()` sempre
   calcula al moment (no es desa a disc per ara).
4. **`/api/filter`**: depèn de `_songs_cache`. Encripta la consulta amb el
   model E5, calcula similituds cosinus, aplica un threshold per percentil 70
   sobre les puntuacions normalitzades min-max, i recalcula projeccions
   t-SNE 2D/3D del subconjunt que sobreviu.
5. **`/api/neighbors`**: troba els N veïns més propers per cosinus, injecta
   el "previous focal" i una mostra de "bridge songs", i fa MDS mètric amb
   distàncies cosinus + rotació de Procrustes per mantenir l'orientació.
