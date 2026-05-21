# `data_pipeline/_label_helpers.py`

Helpers d'utilitat per a la tasca offline de relabel·lar gèneres. No s'invoca des del pipeline principal.

## Constants

| Variable | Valor |
| --- | --- |
| `ROOT` | Arrel del repo. |
| `TOP_5000` | `app/backend/data/processed/top_5000_songs.csv` |
| `AUGMENTED` | `app/backend/data/raw/augmented_songs.csv` |
| `LABELS_CSV` | `app/backend/data/processed/genre_labels.csv` |
| `GENRES` | Mateixa tupla que `_genres.py`. |

## Funcions

| Nom | Què fa |
| --- | --- |
| `normalize(s)` | NFKD + lowercase + collapse spaces. |
| `load_top_5000()` | Llegeix `top_5000_songs.csv` → llista de dicts. |
| `load_lyrics_index()` | Llegeix `augmented_songs.csv` i construeix `key = normalize(artist)+'|'+normalize(title) → {lyrics, description}`. |
| `load_artist_index()` | Variant agrupada per artista. |
| `lookup(artist, title)` | Conveniencia. |
| `short_description(artist, title, max_chars=200)` | Retalla la descripció a `max_chars`. |
| `read_labels_csv()` | Carrega les etiquetes existents (suport per a represa). |
| `append_labels(rows)` | Append-and-flush al CSV. |
| `_load_augmented_raw()` | Helper privat per al lyrics index. |
