# `app/backend/core/embeddings.py`

Scoring per filtre semàntic, similitud cançó–cançó, suggeriments del cercador i construcció de veïnatges. Conté el camí calent `*_fast` (vectoritzat sobre el cub dens) i variants legacy per llistes ad-hoc.

## Constants reexposades des de `config.py`

`GENRE_WEIGHT`, `QUERY_PERCENTILE`, `SIMILAR_PERCENTILE`, `SIMILAR_FIELDS`, `SIMILAR_FIELD_POWER`, `SIMILAR_GATE_POWER`, `SUGGESTION_FIELDS`, `SUGGESTION_COSINE_FLOOR`, `ARTIST_FIELD_IDX`, `GROUP_SUGGESTION_COSINE_FLOOR`. Documentades a [config/](../config/).

## Funcions actives (en producció)

| Nom | Què fa |
| --- | --- |
| `filter_embeddings_fast(query_text, song_ids, index)` | Filtre progressiu per text. Computa similitud sobre tot el catàleg visible (no només `song_ids`) — `song_ids` només interseca al final. Retorna `[(row_idx, score)]` ordenat descendentment. |
| `filter_by_similarity_fast(focal_id, song_ids, index, percentile)` | "Cançons similars a X" amb una mitjana auto-ponderada sobre `SIMILAR_FIELDS` + bonus de gèneres. Garanteix focal + un veí mínim. |
| `compute_cercador_suggestions(query_text, index, exclude_ids, exclude_artist_names, …)` | Genera les 3 slots del cercador (`suggestions`, `lyrics_extra`, `group_extra`) en una sola matmul. Camí fallback quan Qdrant no està actiu. |
| `compute_group_extra(q, index, exclude_artist_names)` | Versió econòmica de `group_extra`: només la columna d'artista. S'usa quan Qdrant ja respon les altres slots. |
| `build_neighborhood(focal_id, all_songs, n, previous_song_id, bridge_song_ids, bridge_count)` | Combina top-N veïns, prev focal i bridges. Usada per `/api/neighbors`. |
| `get_nearest_neighbors(focal_id, songs, n)` | Top-N veïns d'una cançó dins d'una llista (single-field cosinus). |

## Funcions privades de suport

| Nom | Què fa |
| --- | --- |
| `_word_overlap_filter_fast(query_text, sub_idx, songs)` | Fallback per text-overlap quan el model no respon. |
| `_genre_bonus(focal_profile, songs)` | Bonus de gèneres clipat a `[0, 1]` per a `get_nearest_neighbors`. |

## Idees de scoring rellevants

- **Late fusion multi-camp**: el score per cançó és el max-de-camps de cosinus, amb mean-centering per camp perquè els 5 camps siguin comparables (un camp curt com el títol té un baseline diferent que les lletres).
- **Threshold per percentil global**: el llindar es calcula sobre tot el catàleg visible (no sobre `song_ids`), perquè compondre xips sigui commutatiu (`[A, B]` i `[B, A]` retornen els mateixos supervivents).
- **Bonus de gèneres**: centroide dels gèneres dels líders top-K com a estimació del "gènere implicat per la query", amb pes `GENRE_WEIGHT`.
- **Floors absoluts**: `SUGGESTION_COSINE_FLOOR=0.40` per `suggestions`/`lyrics_extra` i `GROUP_SUGGESTION_COSINE_FLOOR=0.60` per `group_extra` (el camp `embedded_artist` és només una codificació del nom; cosinus baix = soroll lèxic).
