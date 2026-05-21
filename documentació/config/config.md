# `config.py`

Font única de constants ajustables per a tot el projecte. Cada secció té el seu corresponent destí al codi.

## Per què viu a l'arrel

Per separar "configuració per experimentar" del codi de producció. Els flags CLI als steps (`--alpha-genre`, `--method`) anul·len aquests defaults per a un run puntual.

## Constants NO incloses aquí (i per què)

- `MODEL_NAME`, `MODEL_DIM`, `PASSAGE_PREFIX` — viuen a `app/backend/core/encoder.py` perquè canviar-los implica regenerar `embedded_songs.parquet`. Mantenir-los junts evita que es desfasin.
- `batch_size` dels parquets — detall d'implementació, no aporta valor exposar-lo.
- Stopwords del cercador (`_STOPWORDS` a `cercador_index.py`) — llista tancada de paraules buides catalanes, no un knob.

## Seccions

### Pipeline (steps 2-6)
| Variable | Default | Significat |
| --- | --- | --- |
| `PIPELINE_TOP_N` | 5000 | Quantes cançons surten al top. |
| `PIPELINE_PROJECTION_METHOD` | `"umap"` | Backend de step6 (`umap`/`tsne`/`pca_umap`). |
| `PIPELINE_PCA_DIM` | 50 | Pre-reducció per t-SNE / pca_umap. |
| `PIPELINE_GENRE_MODE` | `"soft"` | Com participa el bloc de gèneres al layout. |
| `PIPELINE_ALPHA_GENRE` | 0.2 | Pes del bloc gèneres a la distància quadrada. |

### Embedding scoring (`app/backend/core/embeddings.py`)
| Variable | Default | Significat |
| --- | --- | --- |
| `GENRE_WEIGHT` | 0.15 | Bonus màxim de gèneres sobre el score normalitzat. |
| `QUERY_PERCENTILE` | 90.0 | Llindar de supervivents per als xips de text. |
| `SIMILAR_PERCENTILE` | 50.0 | Llindar per als xips de similitud cançó-cançó. |
| `SIMILAR_FIELDS` | `(0, 1, 2, 4)` | Camps que entren a la similitud (skip d'`album`). |
| `SIMILAR_FIELD_POWER` | 4.0 | Power del self-weighted mean. |
| `SIMILAR_GATE_POWER` | 0.5 | Gate del max-camp. |
| `SUGGESTION_FIELDS` | `(0, 1, 2)` | Camps per les suggeriments (lyrics, qualitative, title). |
| `SUGGESTION_COSINE_FLOOR` | 0.40 | Pis absolut per a suggerències + lyrics_extra. |
| `ARTIST_FIELD_IDX` | 4 | Índex del camp `embedded_artist`. |
| `GROUP_SUGGESTION_COSINE_FLOOR` | 0.60 | Pis més alt per group_extra. |
| `CERCADOR_SUGGESTIONS_K` | 4 | Quants suggeriments mostrar. |
| `CERCADOR_LYRICS_EXTRA_K` | 2 | Quants lyrics_extra mostrar. |

### Visible window (`app/backend/core/data_loader.py`)
| Variable | Default | Significat |
| --- | --- | --- |
| `VISIBLE_SONG_LIMIT` | 5000 | Sostre per al scatter. |

### Cercador lèxic (`app/backend/core/cercador_index.py`)
| Variable | Default | Significat |
| --- | --- | --- |
| `CERCADOR_LEX_PENALTY_REF` | 100 | Referència del damper per freqüència de wordfreq. |
| `CERCADOR_W_SONG_TITLE/ARTIST/LYRICS` | 1.6 / 1.3 / 0.8 | Pesos BM25 per camp. |
| `CERCADOR_W_GRUP_NAME` | 1.6 | |
| `CERCADOR_W_NOTI_TITLE/SNIPPET` | 1.6 / 0.4 | |
| `CERCADOR_EXACT_PHRASE_BOOST` | 50.0 | Bonus per coincidència exacta de frase normalitzada. |
| `CERCADOR_RECONSTRUCT_TOP_PER_WORD` | 5 | Fan-out del beam de reconstrucció. |
| `CERCADOR_RECONSTRUCT_BEAM_K` | 32 | Amplada del beam. |
| `CERCADOR_RECONSTRUCT_MIN_JOINT_PROB` | 0.05 | Pis de probabilitat conjunta. |
| `CERCADOR_TOP_GRUPS/SONGS/NOTICIES` | 5 / 8 / 5 | Top-K per col·lecció a la resposta. |
| `CERCADOR_PHRASE_RERANK_TOP_N` | 120 | Quants candidats reranking d'edit-distance. |
| `CERCADOR_PHRASE_RERANK_WEIGHT_TITLE/ARTIST` | 18.0 / 12.0 | Pes del bonus al rerank. |
| `CERCADOR_PARSER_TOP_K` | 20 | Top-K per paraula del parser. |

### Parser (`app/backend/core/parser2.py`)
Veure [backend-core/parser2.md](../backend-core/parser2.md) per al detall de cada `PARSER_COST_*`, `PARSER_DECAY`, `PARSER_*_DISTANCE`, etc.
