# Semantic Song Search Engine

Motor de cerca semàntica per al catàleg de cançons catalanes de [Viasona](https://www.viasona.cat): scatter 2D, filtres en cadena per xips, cercador instantani estil Viasona amb suggeriments semàntics.

## Stack

- **Backend**: FastAPI + bge-m3 (transformers) + Qdrant + pandas/pyarrow.
- **Frontend**: React 19 + Vite.
- **Pipeline offline**: scripts a `data_pipeline/` que generen tots els parquets que el backend serveix.

## Per on començar

Tens **dues coses**: aquest repo (codi) i un paquet de dades a part (`dades.zip` — uns 11 GB). Cap dels dos serveix sol.

1. Demana `dades.zip` a la persona que t'ha passat el repo.
2. Tria la teva guia segons el sistema operatiu:
   - [`README_LINUX.md`](README_LINUX.md) — Ubuntu / Debian natiu.
   - [`README_WSL.md`](README_WSL.md) — Windows 10/11 amb WSL2 (recomanat per Windows).
   - [`README_WINDOWS.md`](README_WINDOWS.md) — Windows natiu amb PowerShell.

Les tres guies són **seqüencials**: de `git clone` a obrir `http://localhost:5173` al navegador. Si saltes passos, no funciona.

## Què hi ha a `dades.zip`

L'arxiu pesa **~10 GB** i conté tres parts:

```
dades.zip
├── raw/
│   ├── embedded_songs.parquet          # 5.2 GB — bge-m3 per-camp, catàleg sencer
│   ├── augmented_songs.csv             # 120 MB — taula de cançons
│   ├── entrances_exits.csv             # 8 MB   — export GA4 (popularitat)
│   ├── cancons.csv                     # 90 MB  — dump DB Viasona
│   ├── grups.csv                       # 2 MB   — dump DB Viasona
│   └── noticies.csv                    # 14 MB  — dump DB Viasona
├── embedded_songs_dataset/             # 1.9 GB — batches d'embeddings per a Qdrant qualitative
│   └── batch_*.parquet
└── snapshots/
    └── songs_lyrics_chunks-*.snapshot  # 3.3 GB — col·lecció Qdrant de chunks de lletra
```

| Carpeta del zip | Destí dins del repo |
|---|---|
| `raw/*` | `app/backend/data/raw/` |
| `embedded_songs_dataset/*` | `ml/embeddings/embedded_songs_dataset/` |
| `snapshots/*.snapshot` | `~/snapshots/` (Linux/WSL) o `qdrant_storage/snapshots/` (Docker) |

## Per què cal el snapshot

Qdrant guarda dues col·leccions:

- **`songs_qualitative`** (86k punts) — barata d'indexar localment (~2 min, sense GPU) a partir dels parquets de `embedded_songs_dataset/`.
- **`songs_lyrics_chunks`** (743k punts) — **cara**: requereix passar bge-m3 per cada chunk. Hores en CPU, minuts amb GPU. Per això es reparteix com a *snapshot* ja generat i la persona nova el restaura amb un `curl`.

Si la persona nova té una GPU i prefereix re-indexar des de zero, vegeu [`DEV_NOTES_QDRANT.md`](DEV_NOTES_QDRANT.md).

## Documentació

- [`DEV_NOTES_QDRANT.md`](DEV_NOTES_QDRANT.md) — Procediment de *rebuild des de zero*, instruccions per refrescar el snapshot, com empaquetar un nou `dades.zip` per repartir.
- [`documentació/`](documentació/) — Descripció fitxer per fitxer de cada mòdul.

## Llicència

Propietat del projecte d'enginyeria de l'UPC. Veure el repositori original.
