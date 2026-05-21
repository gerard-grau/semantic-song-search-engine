# `app/backend/core/data_loader.py`

Càrrega i caching de metadades + embeddings. Construeix l'**índex dens visible** que és el camí calent dels filtres.

## Fitxers que llegeix

| Variable | Path | Origen |
| --- | --- | --- |
| `_PARQUET` | `app/backend/data/raw/embedded_songs.parquet` | Embeddings complets (vé del `dades.zip`). |
| `_AUGMENTED` | `app/backend/data/raw/augmented_songs.csv` | Catàleg augmentat (vé del `dades.zip`). |
| `_CANCONS` | `app/backend/data/raw/cancons.csv` | Dump de BD (data_pipeline step1). |
| `_PARQUET_TOP5000` | `…/processed/embedded_songs_top5000.parquet` | data_pipeline step3. |
| `_PARQUET_2D` | `…/processed/embedded_songs_2d.parquet` | data_pipeline step6. |
| `_META_PARQUET` | `…/processed/songs_meta.parquet` | data_pipeline step5. Preferit sobre CSVs. |
| `_GENRES_PARQ` | `…/processed/embedded_songs_genres.parquet` | data_pipeline step4. |

## Constants exposades

| Nom | Valor | Significat |
| --- | --- | --- |
| `EMBEDDING_FIELD_COLUMNS` | `("embedded_lyrics", "embedded_qualitative_description", "embedded_title", "embedded_album", "embedded_artist")` | Ordre dels camps a la matriu `(F, D)`. |
| `VISIBLE_SONG_LIMIT` | `config.VISIBLE_SONG_LIMIT` (=5000) | Sostre del scatter. |

## Funcions públiques

| Nom | Què fa |
| --- | --- |
| `load_all_songs()` | Metadades de totes les cançons del parquet complet (~80k). Snapshot-first; si falta `songs_meta.parquet` cau a CSV stream. |
| `load_visible_songs()` | Metadades de les cançons visibles (ordenades segons `embedded_songs_2d.parquet`, capades a `VISIBLE_SONG_LIMIT`). Cached. |
| `select_top_songs(songs, limit)` | Política de selecció del subset visible (avui simple: primeres `limit` files). |
| `get_song_by_id(song_id)` | Lookup ràpid per id. |
| `get_songs_by_ids(song_ids)` | Lookup batch. |
| `attach_embeddings(songs)` | Omple `embedding_fields` (matriu `(F, D)`) i `embedding` (vector lletres) in-place. Idempotent. |
| `attach_genre_profiles(songs)` | Omple `genre_profile` (softmax sobre gèneres) in-place. |
| `get_genre_profile(song_id)` | Versió 1 a 1. |
| `load_embeddings_for_ids(ids)` | Lectura streaming del parquet d'embeddings per als ids demanats, amb cache de procés. |
| `get_visible_index()` | **Camí calent.** Construeix una vegada un dict amb `matrix(N,F,D)`, `valid(N,F)`, `genre_matrix(N,G)`, `id_to_idx`, `songs`, tot L2-normalitzat. |
| `invalidate_cache()` | Buida totes les caches in-memory; cridada quan es regenera un parquet. |

## Helpers privats

| Nom | Què fa |
| --- | --- |
| `_embedding_to_list / _array(val, dim)` | Parsing tolerant d'una cel·la d'embedding (bytes, string `[...]`, llista). Retorna zeros si falla. |
| `_extract_year(val)`, `_format_duration(val)` | Sanitització de columnes mixtes. |
| `_parquet_ids(path)` / `_ordered(path)` | Llegeix només la columna `id_lyrics`. |
| `_iter_csv_rows(...)` | Streamer CSV tolerant a files malformades, amb filtrat per `wanted_ids`. |
| `_load_metadata_for_ids(ids)` | Fallback CSV → llista de dicts, per quan no hi ha snapshot parquet. |
| `_read_meta_snapshot()` | Lectura ràpida de `songs_meta.parquet` → llista de dicts. |
| `_load_genre_profiles()` | `id → np.ndarray(G,)` softmax dels gèneres. |
| `_embeddings_source()` | Tria entre el parquet top-5000 i el complet. |
| `_ensure_all_metadata()` | Inicialitza les caches globals (snapshot-first). |

## Cache global

| Variable | Què guarda |
| --- | --- |
| `_all_metadata_cache`, `_all_id_index` | Totes les metadades + index per id. |
| `_visible_metadata_cache`, `_visible_id_index` | Metadades visibles + index per id. |
| `_embedding_cache` | `id → (F, D)` matriu d'embeddings. |
| `_genre_profile_cache` | `id → (G,)` softmax. |
| `_visible_index` | El cub dens construït per `get_visible_index()`. |
