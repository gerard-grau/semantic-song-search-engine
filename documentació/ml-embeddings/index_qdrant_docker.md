# `ml/embeddings/index_qdrant_docker.py`

Indexa els embeddings del catàleg al Qdrant local en docker. Crea dues col·leccions:

- `songs_qualitative` — un punt per cançó amb el vector `embedded_qualitative_description` (1024-dim BGE-M3). Reutilitza els vectors ja calculats als batches parquet de `embedded_songs_dataset/` — no torna a embeggir.
- `songs_lyrics_chunks` — un punt per chunk de ~40 mots (overlap de 20). Re-embeg el text del chunk (recall millorat per a queries curtes).

## Execució

```bash
# 1. Aixecar Qdrant en docker
sudo docker run -d --name qdrant_server \
  -p 6333:6333 -p 6334:6334 \
  qdrant/qdrant

# 2. Indexar
python -m ml.embeddings.index_qdrant_docker
python -m ml.embeddings.index_qdrant_docker --only-qualitative
python -m ml.embeddings.index_qdrant_docker --only-lyrics
python -m ml.embeddings.index_qdrant_docker --only-lyrics --resume
```

Si el `dades.zip` ja porta el volum Qdrant pre-poblat, aquest pas no cal: només ha de muntar el volum al contenidor.

## Funcions

| Nom | Què fa |
| --- | --- |
| `main()` | Argparse + `QdrantClient` + dispatch a una o les dues funcions d'indexació. |
| `index_qualitative(client)` | Crea/recrea la col·lecció `songs_qualitative` amb named vectors (`embedded_title`, `embedded_qualitative_description`) i hi escriu un punt per cançó. |
| `index_lyrics_chunks(client, resume=False)` | Chunkeja les lletres, codifica amb bge-m3 i hi escriu un punt per chunk. Suport per `--resume` via fitxer de progrés. |
| `_chunk_lyrics(lyrics)` | Genera chunks de ~40 paraules amb solapament de 20. |
| `_gen_id(val)` | Genera un UUID determinista per string (per claus de punt estables). |
| `_normalise(vec)` | L2 normalize d'una llista. |
| `_load_meta_csv()` | Carrega `top_5000_songs.csv` per recuperar `title`, `artist`, `genre`, etc. |
| `_read_progress()`, `_write_progress(song_i)`, `_clear_progress()` | Persistència del progrés per a resumar la indexació de lletres si es talla. |
