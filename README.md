# Semantic Song Search Engine

Motor de cerca semàntica per al catàleg de cançons catalanes de [Viasona](https://www.viasona.cat): scatter 2D, filtres en cadena per xips, cercador instantani estil Viasona amb suggeriments semàntics.

## Stack

- **Backend**: FastAPI + bge-m3 (transformers) + Qdrant (docker) + pandas/pyarrow.
- **Frontend**: React 19 + Vite 8.
- **Pipeline offline**: scripts a `data_pipeline/` que generen tots els parquets que el backend serveix.

## Setup per sistema operatiu

Cada guia és una **seqüència de comandes** per anar de `git clone` a tenir l'app corrent:

- [`README_LINUX.md`](README_LINUX.md)
- [`README_WSL.md`](README_WSL.md)
- [`README_WINDOWS.md`](README_WINDOWS.md)

## Què hi ha a `dades.zip`

El zip que has de baixar conté **només** el que és car de regenerar:

| Fitxer / carpeta | Destí dins del repo |
| --- | --- |
| `embedded_songs.parquet` | `app/backend/data/raw/embedded_songs.parquet` |
| `augmented_songs.csv` | `app/backend/data/raw/augmented_songs.csv` |
| `entrances_exits.csv` | `app/backend/data/raw/entrances_exits.csv` (export manual de Google Analytics 4) |
| `qdrant_storage/` | `qdrant_storage/` (volum del docker Qdrant pre-poblat) |

La resta es genera amb `python -m data_pipeline.execute_all` un cop tens aquests dos fitxers i `.env` apuntant a la BD.

## Documentació

La carpeta [`documentació/`](documentació/) descriu fitxer per fitxer què fa cada mòdul (backend-api, backend-core, data-pipeline, ml-embeddings, frontend, config).

## Llicència

Propietat del projecte d'enginyeria de l'UPC. Veure el repositori original.
