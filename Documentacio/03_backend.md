# 03 — Backend: referència fitxer a fitxer

Tots els camins són relatius a l'arrel del repositori. Les funcions
*privades* (començant amb `_`) també es documenten perquè formen part del
contracte intern dels mòduls i poden ser importades per scripts (com fa
`data_pipeline.py` amb `_run_tsne` i `_songs_to_matrix`).

---

## `app/backend/api/main.py`

Punt d'entrada de l'aplicació FastAPI.

### `lifespan(app)` *(asynccontextmanager)*

Funció d'inicialització executada per FastAPI abans d'acceptar peticions.
Crida `core.encoder.load_encoder()` en un `ThreadPoolExecutor` per no bloquejar
el loop d'`asyncio`. Si la càrrega falla (sense connexió, model corrupte, etc.),
loguea un warning i deixa que `embeddings.filter_embeddings` caigui al
fallback per word-overlap.

### `app` (instància `FastAPI`)

Aplicació amb CORS obert (`*`), els dos routers muntats (`search_router`,
`cercador_router`) i l'endpoint `GET /` que respon `{"status": "ok"}`.

---

## `app/backend/api/schemas.py`

Models Pydantic v2. **Tot canvi en aquests models és un canvi del contracte
amb el frontend** — actualitza `app/frontend/src/api/client.js` i els components
consumidors quan modifiquis aquí.

| Model | Funció |
| --- | --- |
| `SongResult` | Resum d'una cançó per llistes (panell esquerre, scatters). |
| `SongDetail` | Variant completa per al modal (afegeix `full_lyrics`, `url`, `duration`, `language`). |
| `Point2D` / `Point3D` | Punt projectat amb metadades mínimes per pintar. `role` ∈ `{focal, neighbor, previous, bridge}`. |
| `AllSongsResponse` | Resposta de `GET /api/songs`. |
| `FilterRequest` / `FilterResponse` | Parella de `POST /api/filter`. |
| `PreviousPosition` | Coordenades antigues d'una cançó per a la rotació de Procrustes. |
| `NeighborsRequest` / `NeighborsResponse` | Parella de `POST /api/neighbors`. |

---

## `app/backend/api/routes/search.py`

Tots els endpoints "semàntics".

### `_to_result(song: dict) → SongResult`

Adapter dict-domain → Pydantic. Centralitzat per evitar repetir 7 camps a cada
endpoint i perquè les dades de `core/` siguin tipus `dict` (més barat) en
comptes de Pydantic.

### `GET /api/songs` → `AllSongsResponse`

Càrrega inicial. Retorna **totes** les cançons del catàleg més les projeccions
2D i 3D *del dataset complet* (cache permanent dins de `projections.py`). El
frontend l'usa a l'arrencada i quan l'usuari prem "Reset".

### `POST /api/filter` → `FilterResponse`

Filtratge progressiu.

```
body.song_ids is None  →  parteix de TOT el catàleg
body.song_ids = [...]  →  parteix només d'aquestes cançons (els supervivents
                          de la query anterior)
```

Internament:

```
songs = data_loader.get_songs_by_ids(body.song_ids) o load_all_songs()
survivors = embeddings.filter_embeddings(body.query, songs)
projections_2d = projections.compute_tsne_2d(survivors)
projections_3d = projections.compute_tsne_3d(survivors)
```

Si `len(survivors) ≤ 5`, el camp `message` retorna *"Explora les N cançons per tu"*
perquè la UI mostri una vista en mode "showcase" (encara que `SongShowcase.jsx`
és codi mort actualment, vegeu `10_codi_mort_i_millores.md`).

### `POST /api/neighbors` → `NeighborsResponse`

Veïnatge per a l'exploració tipus graf. Crida `embeddings.build_neighborhood`
i `projections.compute_neighborhood_2d`. Quan el client envia
`previous_positions`, l'algorisme MDS aplica una rotació de Procrustes perquè
les cançons que apareixen en la pantalla anterior conservin la mateixa
posició → l'usuari percep continuïtat de moviment.

### `GET /api/songs/{song_id}` → `SongDetail`

Detall d'una cançó (popup). 404 si no existeix.

---

## `app/backend/api/routes/cercador.py`

Pestanya tipus Google instant search (cerca textual amb correcció ortogràfica
i autocompletat). **No** usa embeddings.

### Singletons amb càrrega mandrosa

- `_noticies_cache` (notícies de `noticies.csv`, només les 10 000 més recents)
- `_grups_cache` (tots els grups de `grups.csv`)
- `_parser` (instància de `searchoptimal.parser.CatalanSongQueryParser`,
  carregada amb `min_zipf=2.4` i el catàleg combinat de cançons + grups + notícies)

### `_safe_str(val) → str`

Sanejador defensiu per a valors de pandas: tracta `None`, `NaN`, strings
literals `"nan"` / `"NaN"` / `"None"`. Es fa servir a tots els CSV-readers
del fitxer.

### `_get_noticies()`, `_get_grups()`

Carreguen els CSV una sola vegada per procés. Capturen excepcions i retornen
una llista buida si el fitxer falla — així el cercador continua funcionant
encara que les dades de notícies/grups no estiguin disponibles.

### `_get_parser()`

Inicialitza el `CatalanSongQueryParser` amb totes les entrades del catàleg
(cançons + grups + notícies). El `sys.path.insert` puja `searchoptimal/` perquè
el mòdul `parser` es pugui importar sense fer un paquet pip.

### `_normalize_for_match(text)`

Versió lleugera de la normalització: lower + NFKD + treure combinants + treure
`·`. Es fa servir per comparar substrings ("buhos" vs "Bûhos" matchegen).

### `GET /api/cercador?q=...`

Implementa el contracte:

```json
{
  "grups":      [{...}],         // màx. 5
  "cancons":    [{...}],         // màx. 8
  "noticies":   [{...}],         // màx. 5
  "correction": {                // null si no hi ha correcció
    "corrected":  "Boig per tu",
    "suggestions": ["Sopa de Cabra L'Empordà", ...]
  }
}
```

Algorisme:

1. Normalitza la query.
2. La passa pel parser (`top_k_suggestions=4`).
3. Construeix un conjunt de termes de cerca: query original + corregida +
   paraules de la corregida (≥4 caràcters) + artist/title detectats.
4. Per a cada grup, cançó i notícia, comprova si algun terme apareix com a
   substring de la versió normalitzada del camp.
5. Si el parser ha detectat un `matched_artist` o `matched_title`, el
   prioritza posant-lo davant del resultat.
6. Retalla a 5 / 8 / 5.

---

## `app/backend/core/data_loader.py`

Càrrega de cançons (singleton procés).

### Constants

- `_DATA_DIR = app/backend/data`
- `_PARQUET = embedded_songs.parquet` — embeddings per id_lyrics
- `_AUGMENTED = augmented_songs.csv` — text/metadades enriquides
- `_CANCONS = cancons.csv` — exportada de Viasona (data, durada, link)
- `_MOCK = mock_songs.json` — fallback amb embedding 32-d

### Caches

- `_songs_cache: list[dict]` — cançons completes
- `_id_to_song_cache: dict[int, dict]` — índex id→cançó (omplert alhora)

### Helpers privats

- `_fix_bom_columns(df)` — neteja BOM/garbage del nom de columnes (les CSV
  exportades de MariaDB poden venir amb caràcters strange).
- `_embedding_to_list(val)` — accepta `list`, string `"[0.1, ...]"` o `None` i
  retorna `list[float]`.
- `_extract_year(val)` — primers 4 caràcters → int; 0 si invàlid/NaN.
- `_format_duration(val)` — converteix `"0 days 00:04:18"` (timedelta de
  pandas) a `"4:18"` o `"1:23:45"`.

### `_load_from_real_data() → list[dict]`

1. Llegeix `embedded_songs.parquet` només amb columnes `id_lyrics` i
   `embedded_lyrics`.
2. Llegeix `augmented_songs.csv` per chunks de 100 000 files i conserva les
   files amb id en el set d'ids del parquet (encoding `latin-1`!).
3. Llegeix `cancons.csv` igual — extreu `data`, `viasona_link`, `durada`. Si
   falla, segueix amb un DataFrame buit.
4. Merge inner amb el parquet (per `id_lyrics`) i left-join amb cancons.
5. Construeix un dict per cançó amb tots els camps que necessita el frontend.

### `_load_from_mock() → list[dict]`

Llegeix `mock_songs.json`. S'usa només si `_load_from_real_data` falla.

### Funcions públiques

- `load_all_songs()` — load+cache; idempotent.
- `_id_to_song()` — retorna el cache; el carrega si encara no s'ha fet.
- `get_song_by_id(song_id)` — *O(1)* gràcies al cache (abans era O(n)).
- `get_songs_by_ids(song_ids)` — preserva l'ordre d'entrada, *O(k)*.

---

## `app/backend/core/encoder.py`

Encoder HuggingFace. **Aquest és l'únic lloc on s'edita per canviar de model**.

### Constants configurables

```python
MODEL_NAME     = "intfloat/multilingual-e5-small"
MODEL_DIM      = 384
QUERY_PREFIX   = "query: "
PASSAGE_PREFIX = "passage: "
```

Si canvies `MODEL_NAME`, `PASSAGE_PREFIX` o `build_song_passage()`, has de
re-executar `scripts/reembed_mock_songs.py` per regenerar les representacions
emmagatzemades.

### `build_song_passage(song) → str`

Format del passatge: `"passage: {title} by {artist}. Genre: {genre}. {snippet}"`.

### `load_encoder() → (tokenizer, model, device)`

Carrega el model un sol cop (singleton procés). Auto-detecta CUDA.

### `_mean_pool(token_emb, attention_mask)`

Mean-pooling estàndard d'embeddings de transformers ignorant els tokens de
padding. Sumat i dividit per la suma de la màscara amb `clamp(min=1e-9)` per
no dividir per zero.

### `encode_query(text) → list[float]`

Afegeix `QUERY_PREFIX`, tokenitza (max 512), pool, L2-normalitza, `.cpu().tolist()`.

### `encode_passages(texts, batch_size=16) → list[list[float]]`

Versió batch per a `scripts/reembed_mock_songs.py`. Imprimeix progrés a stdout.

---

## `app/backend/core/embeddings.py`

Filtratge progressiu i veïnatge.

### `compute_similarity(query_embedding, song_embedding) → float`

Cosinus entre dos vectors. **No s'usa internament** (les funcions de filtre
treballen amb matrius), però es manté com a part de l'API pública per a tests
i scripts.

### `filter_embeddings(query_text, songs) → list[dict]`

Filtre progressiu. Algorisme detallat:

1. Codifica la query (cau a `_word_overlap_filter` si el model no està
   disponible o si la dimensió del song-embedding no encaixa amb la del
   model — detecta el cas de mock data 32-d).
2. Calcula similituds cosinus amb `similarity.cosine_vector`.
3. Normalitza min-max les similituds → `[0, 1]` perquè els scores estan
   *fortament* clusteritzats (amb dominio similar — pop català — el rang
   típic és <0.06, fent inútil un threshold per percentil sense
   normalitzar prèviament).
4. Threshold = percentil 70 dels scores normalitzats. Conserva només els que
   hi van per sobre.
5. Garanteix ≥1 supervivent (la cançó amb score més alt si el filtre
   eliminés tot).
6. Ordena descendent per score.

### `_word_overlap_filter(query_text, songs)`

Fallback quan els embeddings no quadren. Score = fracció de paraules de la
query que apareixen al text concatenat de la cançó (mapejat a `[0.1, 0.9]`).
Threshold = mediana.

### `build_neighborhood(focal_id, all_songs, n, previous_song_id, bridge_song_ids, bridge_count) → list[dict]`

Genera la llista de cançons per a la pantalla d'exploració:

- **focal**: la cançó central (rol `focal`).
- **neighbors**: les `n` cançons més properes per cosinus.
- **previous**: la cançó d'on venia l'usuari (sempre s'inclou; si ja era veïna
  natural, només se li canvia el rol).
- **bridge**: fins a `bridge_count` cançons del veïnatge anterior, escollides
  per similitud al focal — donen continuïtat visual entre passos.

El càlcul de bridges és **vectoritzat** (matriu d'embeddings dels candidats × focal).

### `get_nearest_neighbors(focal_id, songs, n=20) → list[dict]`

KNN per cosinus. Vectoritzat: una sola matmul calcula totes les similituds.

---

## `app/backend/core/projections.py`

Reducció de dimensió per a visualització.

### `_songs_to_matrix(songs)`

Apila la columna `embedding` de cada song dict en un `np.ndarray` `(n, k)`.

### `_run_tsne(matrix, n_components)`

Wrapper de `sklearn.manifold.TSNE` amb maneig de casos límit:

- `n ≤ 1` → retorna `np.zeros`.
- `n < 4` → init `random` + perplexity = `max(1, n-1)`.
- `n ≥ 4` → init `pca` + perplexity = `min(30, n-1)`.

`random_state=42` per estabilitat entre crides.

### `_build_points(songs, coords, dims)`

Combina metadades i coordenades en dicts amb claus `id`, `x`, `y` (`z` si 3D),
`title`, `artist`, `genre`, `role`. Coordenades arrodonides a 4 decimals.

### `compute_tsne_2d(songs)` / `compute_tsne_3d(songs)`

Versions públiques: `_songs_to_matrix → _run_tsne → _build_points`.

### `_load_precomputed_2d()`

Carrega `embedded_songs_2d.parquet` (generat per `data_pipeline.py`) i hi
afegeix metadades de `data_loader`.

### `get_all_projections_2d()` / `get_all_projections_3d()`

Cache de tot el dataset. La 2D s'intenta carregar des del parquet pre-calculat;
si no existeix o falla, calcula t-SNE al moment. La 3D sempre es calcula al
moment (no hi ha versió pre-calculada a disc).

### `compute_neighborhood_2d(songs, focal_id, previous_song_id, previous_positions)`

Layout d'un veïnatge per a l'exploració:

1. Matriu de **distàncies cosinus** `1 - cosine_matrix(M)` (helper compartit).
2. **MDS mètric** amb `dissimilarity="precomputed"`, `init="random"`,
   `random_state=42`. Per `n ≤ 30` fa 4 reinicis (`n_init=4`); per sobre, 1.
3. Centra al focal restant les coordenades del focal a totes.
4. Escala perquè el percentil 75 de les distàncies no-focal valgui 1.0.
5. **Procrustes**: si tenim posicions antigues, troba la rotació R (det=+1)
   que millor mapeja les posicions noves a les velles per a les cançons
   d'overlap, l'aplica a tot el conjunt, i fa "snap" exacte de cada cançó
   d'overlap a la seva posició antiga. Resultat: les cançons noves van a
   la posició MDS rotada, les velles a la posició exacta anterior.

### `invalidate_cache()`

Buida `_cached_all_2d` i `_cached_all_3d`. Útil si recarregues el corpus en
calent (no s'usa en cap endpoint actual).

---

## `app/backend/core/similarity.py` *(nou)*

Helpers vectorials compartits:

- `l2_normalize_matrix(M)` — normalitza files; deixa intactes les de norma 0.
- `l2_normalize_vector(v)` — variant escalar.
- `cosine_matrix(M)` — `(n, n)` similituds dins del conjunt; clip `[-1, 1]`.
- `cosine_vector(q, M)` — `(n,)` similituds query↔conjunt; vector zero si la
  query té norma 0.

S'utilitza des d'`embeddings.py` i `projections.py`. Centralitzar aquí evita
3-4 còpies de la mateixa lògica de normalització en versions lleugerament
diferents.

---

## `app/backend/core/data_pipeline.py`

Script offline. Genera `embedded_songs_2d.parquet` (t-SNE 2D pre-calculat) a
partir d'`embedded_songs.parquet`.

```bash
python -m app.backend.core.data_pipeline --limit 1000   # opcional
```

Usa les funcions privades `_songs_to_matrix` i `_run_tsne` de `projections.py`.

---

## `app/backend/core/data_getter.py`

ETL de la base de dades Viasona (MariaDB) → 3 CSV. Documentat a fons a
[`06_etl_i_dades.md`](06_etl_i_dades.md).

---

## Fitxers `core/` deprecats

- `app/backend/core/get_songs.py` — versió antiga del getter; té credencials
  hardcoded i conté mojibake (caràcters trencats per encoding). **No
  s'importa enlloc.**
- `app/backend/core/retrieval_functions.py` — utilitats `id2emb`, `id2content`,
  `id_2Demb` per consultar parquets/CSV per id. **No s'importa des dels
  routes.**

Veure [`10_codi_mort_i_millores.md`](10_codi_mort_i_millores.md) per al pla
de neteja.
