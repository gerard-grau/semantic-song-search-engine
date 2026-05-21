# `app/backend/core/qdrant_search.py`

Client Qdrant per al cercador semàntic. Es connecta a `localhost:6333` i degrada amablement a `None` si el servidor no respon, perquè la ruta `/api/cercador/suggestions` pugui caure al fallback per matriu sense errors a l'usuari.

## Constants

| Variable | Valor | Significat |
| --- | --- | --- |
| `QDRANT_HOST` / `QDRANT_PORT` | `"localhost"` / `6333` | Endpoint del docker local. |
| `_TIMEOUT` | `30.0` | Segons per request (exact search 780k chunks). |
| `QUALITATIVE_COLLECTION` | `"songs_qualitative"` | Un punt per cançó, vector de descripció qualitativa. |
| `LYRICS_COLLECTION` | `"songs_lyrics_chunks"` | Un punt per chunk de ~40 mots. |
| `_SCORE_THRESHOLD` | `0.28` | Cosinus mínim per resultats dense. |
| `_RRF_K` | `60` | Constant de Reciprocal Rank Fusion estàndard. |
| `_CE_MODEL_NAME` | `"cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"` | Cross-encoder per al rerank. |

## API pública

| Funció | Què fa |
| --- | --- |
| `is_available()` | True si Qdrant respon i les dues col·leccions existeixen. |
| `search_qualitative(query_vec, limit, artist_filter, exclude_ids)` | Cerca a `songs_qualitative` (mood/temàtica). |
| `search_by_title(query_vec, limit, artist_filter, exclude_ids)` | Cerca pel vector `embedded_title` named-vector dins de la mateixa col·lecció (requereix esquema modern). |
| `search_lyrics_chunks(query_vec, limit, artist_filter, exclude_ids, query_text)` | Cerca híbrida dense + keyword + RRF + cross-encoder. Retorna chunks dedup per cançó. |

Totes retornen `list[dict]` o `None` (= Qdrant no disponible). Llista buida = sense resultats per sobre del threshold.

## Internals

| Nom | Què fa |
| --- | --- |
| `_get_client()` | Cache amb retry exponencial (`_RETRY_INTERVAL = 30s`) per no spamejar el server caigut. |
| `_drop_client()` | Marca el client com a caigut. |
| `_detect_qualitative_schema(client)` | Detecta named-vectors vs single-unnamed-vector (legacy). |
| `_get_cross_encoder()` | Lazy-load del CrossEncoder. |
| `_ce_rerank(query_text, candidates, top_k)` | Re-puntua amb sigmoid sobre logits crus. |
| `_ensure_text_index(client)` | Crea l'índex full-text sobre `chunk_text_snippet` (idempotent). |
| `_payload_filter(artist)` | Filtre MatchAny sobre variants normalitzades del nom. |
| `_extract_keywords(text)` | Tokens ≥3 chars que no estiguin a `_STOP_WORDS` (mix CA/ES), cap 6. |
| `_keyword_lyrics_search(...)` | Cerca dense filtrada per keywords AND, amb fallback degradat (baixant 1 keyword a la vegada). |
| `_rrf_fuse(dense, keyword, limit, k_dense)` | RRF asimètric: keyword k_kw escala amb keywords matched (6/21/36/51). |

## Pipeline `search_lyrics_chunks` quan `query_text` està present

1. Dense fetch d'`limit × 20` candidats amb threshold = 0.
2. Keyword-filtered dense search (AND amb tokens significatius).
3. RRF asimètric entre les dues llistes (frase exacta domina).
4. Cross-encoder rerank sobre el top-30.
5. Dedup final per `(artist, title)`.
