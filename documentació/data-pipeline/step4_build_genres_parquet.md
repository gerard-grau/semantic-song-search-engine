# `data_pipeline/step4_build_genres_parquet.py`

Construeix `embedded_songs_genres.parquet`: un one-hot per cançó del top 5000 sobre la taxonomia de 9 gèneres.

## Esquema de l'output

| Columna | Tipus | Contingut |
| --- | --- | --- |
| `id_lyrics` | int64 | id que coincideix amb el parquet d'embeddings. |
| `genre` | str | Slug del gènere (vegeu `_genres.py`). |
| `genre_scores` | list[float] | One-hot alineat amb l'ordre de `GENRES`. |

## Funcions

| Nom | Què fa |
| --- | --- |
| `run(default_genre="folk", force=False)` | Pipeline: per cada fila de `embedded_songs_top5000.parquet`, busca per `(title, artist)` el seu rank a `top_5000_songs.csv` i mapeja el rank a `RANK_TO_GENRE[rank]`. Si falta, fa servir `default_genre`. |
| `main()` | Argparse wrap. |
| `_one_hot_table()` | `slug → np.ndarray(len(GENRES),)` one-hot. |
| `_norm_key(s)` | NFKD + lowercase + collapse spaces. |
