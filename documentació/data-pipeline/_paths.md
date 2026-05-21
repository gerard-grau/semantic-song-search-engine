# `data_pipeline/_paths.py`

Centralitza tots els paths del pipeline. Qualsevol step que necessiti llegir o escriure dades els importa d'aquí.

## Estructura del filesystem

```
app/backend/data/
├── raw/        — inputs externs: dumps de BD, embeddings massius,
│                  exports manuals. Mai sobreescrits pel pipeline.
└── processed/  — artefactes computats pels steps 2-6. Segurs d'esborrar.
```

## Constants exposades

| Nom | Path |
| --- | --- |
| `REPO_ROOT` | Arrel del repo (un nivell sobre `data_pipeline/`). |
| `DATA_DIR` | `app/backend/data/` |
| `RAW_DIR` | `app/backend/data/raw/` |
| `PROCESSED_DIR` | `app/backend/data/processed/` |
| `ENV_FILE` | `.env` a l'arrel. |
| `AUGMENTED_CSV` | `raw/augmented_songs.csv` |
| `EMBEDDED_PARQUET` | `raw/embedded_songs.parquet` |
| `CANCONS_CSV` | `raw/cancons.csv` |
| `GRUPS_CSV` | `raw/grups.csv` |
| `NOTICIES_CSV` | `raw/noticies.csv` |
| `ENTRANCES_CSV` | `raw/entrances_exits.csv` |
| `TOP5000_CSV` | `processed/top_5000_songs.csv` |
| `TOP5K_PARQUET` | `processed/embedded_songs_top5000.parquet` |
| `GENRES_PARQUET` | `processed/embedded_songs_genres.parquet` |
| `META_PARQUET` | `processed/songs_meta.parquet` |
| `PROJECTION_2D` | `processed/embedded_songs_2d.parquet` |
