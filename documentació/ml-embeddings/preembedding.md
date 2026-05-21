# `ml/embeddings/preembedding.py` *(legacy — primera versió de la generació d'embeddings)*

> **Estat**: script antic que codificava un esquema d'augmented_songs amb columnes `lyrics_chunks`, `noised_chunks`, `noised_title`, `noised_author`. Aquest esquema ja no existeix al CSV actual i la ruta `../augmented_songs.csv` ja no és vàlida.

Avui els `embedded_songs.parquet` es generen amb scripts notebook (no inclosos a la pipeline live) o, a la pràctica, els descarregues pre-fets dins de `dades.zip`.

## Funcions

| Nom | Què feia |
| --- | --- |
| `cls_pool(token_embeddings)` | Selecciona el token CLS (`[:, 0]`). |
| `embed_texts(texts, batch_size=64)` | Forward batch + L2 normalize. |
| `aggregate_chunk_embeddings(chunks)` | Mean pooling. |
| `preembed_songs(csv_path, output_path)` | Itera files, calcula 6 embeddings per cançó (lletres + noised lletres + títol + noised títol + autor + noised autor) i guarda amb `torch.save`. |

## Notes de manteniment

- No depèn de cap altre mòdul del repo (té el seu propi `MODEL_NAME`, `BATCH_SIZE`, `DEVICE`).
- El producte final que el backend consumeix és `embedded_songs.parquet` (taula plana per columnes per camp), no el `.pt` que produeix aquest script.
- Si vols regenerar el parquet de zero, és millor partir d'un notebook nou que escrigui directament a parquet en l'esquema esperat per `data_loader.py` (`embedded_lyrics`, `embedded_qualitative_description`, `embedded_title`, `embedded_album`, `embedded_artist`).
