# `data_pipeline/` — visió general

Pipeline offline que transforma dades crues (BD MariaDB de Viasona + embeddings pre-computats + export GA4) en els artefactes que el backend serveix sense fer cap càlcul costós en temps de petició.

## Diagrama de dependència

```
                .env
                  │
                  ▼
              ┌─ step1 (DB → raw CSVs) ─────┐
              │                              │
augmented_songs.csv ──┐                  cancons.csv
embedded_songs.parquet ┤                  grups.csv
entrances_exits.csv ───┤                  noticies.csv
              │       │                       │
              ▼       ▼                       │
            step2 ── top_5000_songs.csv       │
              │       │                       │
              ▼       ▼                       │
            step3 ── embedded_songs_top5000.parquet
              │
              ▼
            step4 ── embedded_songs_genres.parquet
              │
              ▼
            step5 ── songs_meta.parquet  ◄────┘
              │
              ▼
            step6 ── embedded_songs_2d.parquet
```

## Idempotència

Cada step comprova si el seu output ja existeix a `app/backend/data/processed/` i es salta si no s'ha passat `--force`. Així rellançar `execute_all` un cop tens els outputs costa segons (sumant les comprovacions), no minuts.

## Mòduls

| Fitxer | Doc |
| --- | --- |
| `execute_all.py` | [execute_all.md](execute_all.md) |
| `step1_fetch_catalogue_csvs.py` | [step1_fetch_catalogue_csvs.md](step1_fetch_catalogue_csvs.md) |
| `step2_build_top_songs.py` | [step2_build_top_songs.md](step2_build_top_songs.md) |
| `step3_filter_top5000_embeddings.py` | [step3_filter_top5000_embeddings.md](step3_filter_top5000_embeddings.md) |
| `step4_build_genres_parquet.py` | [step4_build_genres_parquet.md](step4_build_genres_parquet.md) |
| `step5_build_meta.py` | [step5_build_meta.md](step5_build_meta.md) |
| `step6_project_2d.py` | [step6_project_2d.md](step6_project_2d.md) |
| `_genres.py` | [_genres.md](_genres.md) |
| `_label_helpers.py` | [_label_helpers.md](_label_helpers.md) |
| `_paths.py` | [_paths.md](_paths.md) |
