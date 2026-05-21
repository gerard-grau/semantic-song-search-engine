# `app/backend/core/cercador_index.py`

Índex invertit del cercador instantani sobre `cancons`/`grups`/`noticies`. Singleton de procés que es construeix una vegada (a `lifespan`) i serveix tota la sessió.

## Constants i pesos (sourced de `config.py`)

| Variable | Significat |
| --- | --- |
| `_STOPWORDS` | Paraules buides catalanes (articles, preposicions, conjuncions, etc.) que es filtren del scoring tret que tots els tokens de la query siguin stopwords. |
| `LEX_PENALTY_REF` | Referència del damper basat en freqüència (wordfreq) per penalitzar paraules comunes. |
| `W_*` | Pesos BM25-style per camp (`title=1.6`, `artist=1.3`, `lyrics=0.8`, etc.). |
| `EXACT_PHRASE_BOOST` | Bonus additiu per coincidència exacta de frase normalitzada. |
| `RECONSTRUCT_*` | Paràmetres del beam search de reconstrucció ("bog per tu" → "boig per tu"). |

## Funcions de mòdul

| Nom | Què fa |
| --- | --- |
| `_safe_str(val)` | Sanititza strings amb NaN/"None"/"nan" → `""`. |
| `_load_grups()` | Llegeix `grups.csv` → `list[dict]` ordenat per nom. |
| `_load_noticies()` | Llegeix `noticies.csv` → `list[dict]`. |
| `get_index()` | Retorna el singleton `CercadorIndex` (construit lazy). |
| `prewarm()` | Crida `get_index()` per pre-warm al `lifespan`. |
| `derive_correction(query, parsed, index, …)` | Construeix l'objecte "Volies dir" només per paraules **desconegudes** (no al catàleg ni al lèxic comú). |

## Classe `CercadorIndex`

| Atribut | Tipus | Contingut |
| --- | --- | --- |
| `songs`, `grups`, `noticies` | `list[dict]` | Les tres taules. |
| `songs_idx`, `grups_idx`, `noticies_idx` | `dict[str, list[(idx, w)]]` | Índex invertit per token amb pes de camp. |
| `*_phrase` | `dict[str, list[int]]` | Frase normalitzada → ids per a boost de coincidència exacta. |
| `_*_norm` | `list[str]` | Frase normalitzada paral·lela a la taula (per al rerank d'edit-distance). |
| `parser` | `Parser2` | Lèxic compartit per typo correction. |
| `catalog_tokens` | `set[str]` | Tokens reals del catàleg, usats per `derive_correction`. |

### Mètodes

| Nom | Què fa |
| --- | --- |
| `build()` | Carrega les tres taules, omple el lèxic del parser i construeix els índexs. Idempotent. |
| `search(query, top_grups, top_songs, top_noticies)` | Pipeline complet: parser → scoring → boost frase exacta → reconstruction boost (beam) → phrase-edit-distance rerank → top-K dedup. |
| `find_grup_by_name(name)` | Resol un nom d'artista al registre de `grups.csv` via comparació normalitzada. |
| `_index_songs/_grups/_noticies()` | Omplen els respectius índexs. |
| `_enumerate_reconstructions(query)` | Beam-search sobre les distribucions per paraula del Parser2; retorna frases candidates amb la seva probabilitat conjunta. Posicions monocaràcter (com "i") es preserven verbatim. |
| `_phrase_rerank(query, ql, scores, norm_phrases, top_n, weight)` | Bonus per edit-distance de frase al top-N candidats. Només funciona si la query té ≥2 tokens. |
| `_score(parsed, idx, n_items, filter_stopwords)` | Implementació del BM25-style scoring (`prob × idf × lex_penalty × field_w`). |
| `_top(scores, items, k, dedup_key)` | Top-K amb dedup opcional. |
