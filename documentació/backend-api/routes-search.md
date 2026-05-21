# `app/backend/api/routes/search.py`

Rutes principals del scatter: catàleg visible, filtre progressiu (chips) i veïnatge per a navegació estil graf.

## Endpoints

| Mètode + URL | Què fa |
| --- | --- |
| `GET /api/songs` | Retorna les `≤ VISIBLE_SONG_LIMIT` cançons del catàleg visible amb les coordenades 2D pre-calculades. Crida `load_visible_songs()` i `get_all_projections_2d()`. |
| `POST /api/filter` | Aplica un xip: si `similar_to_id` està posat, usa `filter_by_similarity_fast`; altrament `filter_embeddings_fast(query, song_ids, index)`. Tots dos operen sobre l'índex dens prebuilt (`get_visible_index()`). |
| `POST /api/neighbors` | Construeix el veïnatge d'una cançó (focal + veïns + previous + bridges) i en projecta la disposició 2D via MDS amb continuïtat Procrustes respecte als posicions anteriors. |
| `GET /api/songs/{song_id}` | Detall complet (incloent `full_lyrics`, `duration`, `url`). |

## Helpers privats

| Nom | Què fa |
| --- | --- |
| `_to_result(song)` | Empaqueta un `dict` de cançó en un `SongResult`. |

## Detalls importants

- L'index `(N, F, D)` que utilitzen els filtres `*_fast` es construeix una vegada al pre-warm (`lifespan`). Cada `/filter` és essencialment una matmul d'una fila contra el cub.
- `/filter` retorna `projections_2d=[]` per estalviar t-SNE per request — el frontend dibuixa el scatter sempre amb les coordenades globals i només aplica un highlight als ids supervivents.
