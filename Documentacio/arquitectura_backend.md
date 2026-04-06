# Arquitectura del Backend

## Tecnologies

- **FastAPI** — framework web asíncron
- **Pydantic** — validació de dades
- **scikit-learn** — t-SNE per projeccions dimensionals
- **NumPy** — operacions amb matrius d'embeddings

## Estructura de fitxers

```
app/backend/
├── api/
│   ├── __init__.py
│   ├── main.py              # Entry point de FastAPI, middleware CORS
│   ├── schemas.py           # Models Pydantic (request/response)
│   └── routes/
│       ├── __init__.py
│       └── search.py        # Endpoints: /api/songs, /api/filter, /api/songs/{id}
├── core/
│   ├── __init__.py
│   ├── data_loader.py       # Càrrega de dades (mock: JSON, real: DB)
│   ├── embeddings.py        # Embeddings + filtratge (mock: substring, real: cosine sim)
│   └── projections.py       # Projeccions t-SNE 2D i 3D
└── data/
    └── mock_songs.json      # 50 cançons catalanes amb embeddings k=32
```

## Mòduls i funcions mock

### `core/data_loader.py`

| Funció | Mock | Real |
|---|---|---|
| `load_all_songs() → list[dict]` | Llegeix `mock_songs.json` i cacheja en memòria | Query a PostgreSQL/Elasticsearch |
| `get_song_by_id(id) → dict \| None` | Cerca lineal a la llista cached | Lookup indexat per primary key |
| `get_songs_by_ids(ids) → list[dict]` | Filtra la llista cached | `WHERE id IN (...)` |

### `core/embeddings.py`

| Funció | Mock | Real |
|---|---|---|
| `text_to_embedding(text) → list[float]` | Vector random de dim 32 (determinista per hash) | `multilingual-e5-large` amb prefix "query: " |
| `compute_similarity(q, s) → float` | Random 0-1 | Cosine similarity: `dot(a,b) / (‖a‖·‖b‖)` |
| `filter_embeddings(query, songs) → list[dict]` | Substring match + 30% retenció random | Cosine sim + threshold adaptatiu + ANN search |

**Comportament del filtratge mock:**
1. Cerca substring (case-insensitive) a títol, artista, lletra, àlbum, gènere
2. Coincidències: score 0.70–1.00
3. No-coincidències: score 0.05–0.40, però només es retenen un ~30% aleatori
4. Mai retorna 0 cançons (mínim 1)
5. Retorna ordenat per score descendent

### `core/projections.py`

| Funció | Descripció |
|---|---|
| `compute_tsne_2d(songs) → list[dict]` | Executa t-SNE (n_components=2) sobre els embeddings k-dim |
| `compute_tsne_3d(songs) → list[dict]` | Executa t-SNE (n_components=3) |
| `get_all_projections_2d() → list[dict]` | Retorna projeccions 2D cached de TOTES les cançons |
| `get_all_projections_3d() → list[dict]` | Retorna projeccions 3D cached |
| `invalidate_cache()` | Buida la cache (si canvien les dades) |

**Detalls del t-SNE:**
- Perplexity: `min(30, n-1)`, mínim 1
- random_state=42 per reproducibilitat
- Si n ≤ 1: retorna coordenades [0,0]
- La cache es calcula una sola vegada per al dataset complet (reset instantani)
- Cada filtratge recalcula t-SNE sobre el subconjunt

## Com substituir els mocks

Per reemplaçar cada funció mock:

1. **`data_loader.py`**: Canvia la lectura del JSON per una connexió a la teva DB (ex: `psycopg2`, `sqlalchemy`)
2. **`embeddings.py`**: Carrega el model `SentenceTransformer("intfloat/multilingual-e5-large")` un cop a l'inici. Implementa cosine similarity real amb numpy o FAISS
3. **`projections.py`**: Si els embeddings ja són molt grans (126k), considera UMAP en lloc de t-SNE, o pre-calcula les projeccions offline

Cada funció té docstrings detallats amb la signatura exacta i el comportament esperat de la implementació real.
