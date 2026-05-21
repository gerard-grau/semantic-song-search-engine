# `data_pipeline/step5_build_meta.py`

Construeix `songs_meta.parquet`: snapshot tabulat amb tota la metadada que `app/backend/core/data_loader.py` espera consumir.

## Esquema de l'output

| Columna | Tipus |
| --- | --- |
| `id` | int64 |
| `title`, `artist`, `album`, `genre`, `language` | str |
| `year` | int |
| `lyrics_snippet`, `full_lyrics`, `url`, `duration` | str |

## Funcions

| Nom | Què fa |
| --- | --- |
| `run(force=False)` | Pipeline: `_build(ids) → _join_genre` → escriu parquet. `ids` són els del parquet d'embeddings sencer. |
| `main()` | Argparse wrap. |
| `_build(ids)` | Streaming per `augmented_songs.csv` i `cancons.csv` per a només els ids demanats; uneix per `id_lyrics ↔ id_lletra`. |
| `_join_genre(songs)` | Enganxa la columna `genre` venint de `embedded_songs_genres.parquet`. |
| `_iter_csv_rows(path, encoding, id_column, wanted_ids, columns)` | Streamer tolerant a files malformades, amb filtre per ids. |
| `_extract_year(val)`, `_format_duration(val)` | Sanitització de mixed-type columns. |
