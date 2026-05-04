# 01 — Visió general

## Què és

**Semantic Song Search Engine** és una aplicació web que permet explorar
un catàleg de cançons catalanes (font: base de dades Viasona) mitjançant
**cerques semàntiques** en llenguatge natural. La interfície té tres
modes complementaris:

1. **Descobridor** (pàgina principal): l'usuari escriu queries lliures
   ("cançons tristes d'amor", "rock català dels 80", etc.) i el catàleg es
   filtra progressivament. Cada query redueix el conjunt actiu i l'aplicació
   recalcula projeccions t-SNE 2D i 3D perquè l'usuari "vegi" l'espai.
2. **Cercador** (pestanya tipus Google instant search): cerca textual sobre
   grups, lletres i notícies amb correcció ortogràfica i autocompletat.
3. **Detall de cançó** (modal): metadades + lletra completa + enllaç a Viasona.

## Tecnologies

| Capa | Stack |
| --- | --- |
| Frontend | React 19 + Vite, deck.gl/Three.js (visualització), axios |
| Backend | FastAPI + uvicorn, Pydantic v2, NumPy, pandas, scikit-learn |
| ML | `intfloat/multilingual-e5-small` via HuggingFace `transformers`, PyTorch |
| Cerca textual | `symspellpy` + `wordfreq` (parser propi a `searchoptimal/`) |
| Dades | Parquet (embeddings + projeccions 2D), CSV (text), MariaDB (font Viasona) |

## Casos d'ús principals

### Cas A — Filtrar progressivament

> *L'usuari obre l'app, escriu "amor i mar" → veu un núvol de cançons →
> escriu "tristesa" → el núvol es redueix → fa clic a una cançó → veu les
> més similars.*

Endpoints implicats:

```
GET  /api/songs                     ← càrrega inicial (totes les cançons + projeccions)
POST /api/filter   {query, song_ids?}  ← filtratge per similitud
POST /api/neighbors {song_id, n, ...}  ← veïnatge d'una cançó
GET  /api/songs/{id}                  ← detall
```

### Cas B — Cerca instant ortogràfica

> *L'usuari escriu "bog per tu" al cercador → es corregeix a "Boig per tu" →
> apareixen els grups, cançons i notícies que contenen aquestes paraules.*

Endpoint implicat:

```
GET /api/cercador?q=...
```

## Flux de dades complet

```
┌──────────────────────────┐
│   MariaDB Viasona        │   (font externa de cançons, grups, notícies)
└────────────┬─────────────┘
             │ data_getter.py (ETL — offline)
             ▼
   ┌──────────────────────┐    ┌──────────────────────┐
   │ noticies.csv         │    │ grups.csv            │
   │ cancons.csv          │    └──────────────────────┘
   └──────────┬───────────┘
              │ ml/embeddings/preembedding.py
              ▼
   ┌──────────────────────────────────┐
   │ embedded_songs.parquet           │  (id_lyrics, embedded_lyrics, …)
   └──────────┬───────────────────────┘
              │ data_pipeline.py
              ▼
   ┌──────────────────────────────────┐
   │ embedded_songs_2d.parquet        │  (id_lyrics, x, y) — t-SNE precomputat
   └──────────────────────────────────┘
              │
              ▼
   FastAPI (lifespan precarrega encoder + dades)
              │
              ▼
   React (axios → /api/...)
```

## Carpeta a carpeta

| Camí | Rol |
| --- | --- |
| `app/backend/api/` | Aplicació FastAPI (rutes + esquemes Pydantic). |
| `app/backend/core/` | Lògica de domini: càrrega de dades, embeddings, projeccions, similitud. |
| `app/backend/data/` | CSV i parquet generats per ETL (no entren a git). |
| `app/frontend/` | Aplicació React (Vite). |
| `searchoptimal/` | Parser de cerca textual amb correcció + completion. |
| `etl/`, `ml/`, `scripts/` | Scripts offline de transformació i re-embedding. |
| `youtube_audio_pipeline/` | Pipeline (mòdul independent) per extreure features d'àudio de YouTube. |
| `Documentacio/` | Aquesta documentació. |
| `tests/` | Esquelet de tests (placeholders). |
| `docs/`, `notebooks/`, `data/`, `design_stuff/` | Material auxiliar (no productiu). |
