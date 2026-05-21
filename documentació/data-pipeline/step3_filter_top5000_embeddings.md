# `data_pipeline/step3_filter_top5000_embeddings.py`

Talla el parquet d'embeddings sencer (~80k cançons, 5.2 GB) a només les 5000 cançons del visible set.

## Funcions

| Nom | Què fa |
| --- | --- |
| `run(force=False)` | Pipeline: llegeix `augmented_songs.csv`, alinia amb `embedded_songs.parquet`, resol per `(title, artist, album)` cada fila del top 5000, escriu el parquet filtrat. |
| `main()` | Argparse wrap. |
| `_load_augmented(path)` | Llegeix el CSV gegant (lyrics tolerants a `csv.field_size_limit` alt). |
| `_align(aug, parquet_path)` | Two-pointer alignment sobre `id_lyrics` entre el CSV i el parquet. Necessari perquè les "collaboracions" comparteixen `id_lyrics` però tenen una fila per artista. |
| `_build_lookups(aug, aug_to_pq)` | Construeix índexs per `(title, artist, album)` i `(title, artist)`. |
| `_album_from_page(page_title)` | Pesca el nom de l'àlbum quan només tenim el títol de pàgina. |
| `_pick(candidates, csv_album)` | Resolució de col·lisions: prefer match exacte d'àlbum, després primer no-buit. |
| `_resolve(top_csv, by_tri, by_pair)` | Per a cada fila del top 5000, troba la fila del parquet corresponent. |
| `_slice(resolved, embed_parquet, output)` | Llegeix només les files seleccionades i escriu el parquet petit. |
| `_norm_key(s)` | NFKD + lowercase + collapse spaces per a comparació tolerant a accents/case. |

## Per què el two-pointer

Algunes cançons (col·laboracions) comparteixen `id_lyrics`. Cada una té la seva pròpia fila al CSV (un artista per fila) i la seva pròpia fila d'embedding al parquet. Si dedupliquéssim només per `id_lyrics` ens quedaríem amb l'embedding de l'artista equivocat. El walk lockstep recupera el mapeig `(fila_csv → fila_parquet)`.
