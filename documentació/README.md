# Documentació del projecte

Aquesta carpeta documenta, fitxer per fitxer, el funcionament del motor de cerca semàntica de cançons catalanes.

## Visió general

El projecte té tres parts:

1. **`data_pipeline/`** — pipeline offline que, a partir de dades crues (BD MariaDB de Viasona + dump GA4 + embeddings pre-computats), genera tots els artefactes `parquet` que l'API serveix.
2. **`app/backend/`** — API FastAPI que respon a cerques semàntiques (`/api/filter`), cerca lèxica (`/api/cercador`), suggeriments amb embeddings (`/api/cercador/suggestions`) i detall de cançons. Carrega tots els artefactes a memòria al llançar.
3. **`app/frontend/`** — SPA en React/Vite amb un scatter 2D, filtres en cadena (chips) i una pàgina cercador a l'estil Viasona.

A més:
- **`ml/embeddings/`** — script offline que codifica el catàleg amb bge-m3 (`preembedding.py`) i el publica a Qdrant local en docker (`index_qdrant_docker.py`).
- **`config.py`** — única font de constants ajustables.

## Mapa de mòduls

| Carpeta | Document |
| --- | --- |
| `app/backend/api/` | [backend-api/](backend-api/) |
| `app/backend/core/` | [backend-core/](backend-core/) |
| `data_pipeline/` | [data-pipeline/](data-pipeline/) |
| `ml/embeddings/` | [ml-embeddings/](ml-embeddings/) |
| `app/frontend/` | [frontend/](frontend/) |
| `config.py` | [config/](config/) |

## Flux de dades, alt nivell

```
                       ┌──────────────────────┐
                       │  MariaDB (Viasona)   │
                       └─────────┬────────────┘
                                 │ step1
                                 ▼
                         cancons / grups /
                          noticies .csv (raw)
                                 │
augmented_songs.csv ─┐   GA4 entrances ─┐
embedded_songs.parq ─┤        │         │
                      └───────┴─ steps 2-6 ─►  embedded_songs_top5000.parquet
                                                embedded_songs_genres.parquet
                                                songs_meta.parquet
                                                embedded_songs_2d.parquet
                                                top_5000_songs.csv
                                                                │
                                                                ▼
                                                       FastAPI (app/backend)
                                                                │
                                                                ▼
                                                       React SPA (app/frontend)

Per al cercador semàntic, els embeddings també s'indexen a
Qdrant (docker) via ml/embeddings/index_qdrant_docker.py.
```

## Codi legacy conservat per referència

- `ml/embeddings/preembedding.py` — primera versió de la generació d'embeddings amb un esquema diferent (`lyrics_chunks`, `noised_*`). Avui els embeddings es regeneren amb scripts notebook o ja venen pre-generats al `dades.zip`. Es manté perquè el procés d'embedding és pesat i hi ha interès històric a saber com es va fer.

## Documentació per fitxer

Cada carpeta `documentació/*/` conté un `.md` per cada fitxer rellevant del mòdul. La descripció segueix sempre el mateix patró: paper del fitxer, taula de funcions/classes públiques, entrades i sortides quan són dades, observacions de manteniment.
