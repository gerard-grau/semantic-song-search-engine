# `data_pipeline/_genres.py`

Llista de gèneres i mapping manual `rank → slug` per a les 5000 cançons del top.

## Taxonomia

```
GENRES = (
  "cançó d'autor", "folk", "tradicional", "rock", "pop",
  "rumba", "música urbana", "infantil", "mestissa",
)
```

## `RANK_TO_GENRE: dict[int, str]`

Diccionari amb les ~5000 entrades, etiquetades manualment a partir del top de Viasona. La font de veritat consolidada és `app/backend/data/processed/genre_labels.csv` (el `_genres.py` és un cache generat).

## Ús

- `step2_build_top_songs.py` afegeix la columna `genre` a `top_5000_songs.csv`.
- `step4_build_genres_parquet.py` el converteix en one-hot per cançó.
- `step6_project_2d.py` (mode `onehot`) o `data_loader._load_genre_profiles` (mode `soft`) llegeixen les distribucions resultants.
