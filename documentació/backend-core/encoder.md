# `app/backend/core/encoder.py`

Punt únic on es decideix amb quin model es codifiquen consultes i passatges. Tots els altres mòduls importen `encode_query` o `encode_passages` d'aquí.

## Configuració (constants al fitxer)

| Nom | Valor | Notes |
| --- | --- | --- |
| `MODEL_NAME` | `"BAAI/bge-m3"` | Multilingual, dense-retrieval. |
| `MODEL_DIM` | `1024` | Ha de coincidir amb les columnes del parquet d'embeddings. |
| `QUERY_PREFIX` | `""` | bge-m3 no usa prefixos. |
| `PASSAGE_PREFIX` | `""` | idem. |

Si canvies aquestes constants, cal regenerar `embedded_songs.parquet` (vegeu `ml-embeddings/preembedding.md`).

## Funcions públiques

| Nom | Què fa |
| --- | --- |
| `build_song_passage(song)` | Genera el text que s'embeggeix per una cançó: `"{title} by {artist}. Genre: {genre}. {lyrics_snippet}"`. |
| `load_encoder()` | Carrega `AutoTokenizer` + `AutoModel` una sola vegada per procés. Detecta CUDA si està disponible. |
| `encode_query(text) -> list[float]` | Codifica una query d'usuari. L2-normalitzat. |
| `encode_passages(texts, batch_size=16) -> list[list[float]]` | Codifica un batch de passatges (amb barra de progrés simple). |

## Detalls de pooling

La capa `_cls_pool` retorna el token `[CLS]` de la última hidden layer (`out.last_hidden_state[:, 0]`). És l'esquema oficial de bge-m3 per al cap dense-retrieval.

## Cache de procés

`_tokenizer`, `_model`, `_device` es resolen una sola vegada. La crida `load_encoder()` és idempotent.
