# `app/backend/core/projections.py`

Maneja les coordenades 2D del scatter. Per al catàleg sencer s'usa la projecció pre-calculada al disc; per a veïnatges (subconjunts petits) es recalcula amb MDS al moment.

## Fitxers

| Variable | Path |
| --- | --- |
| `_PRECOMP_2D` | `app/backend/data/processed/embedded_songs_2d.parquet` (data_pipeline step6) |

## Funcions

| Nom | Què fa |
| --- | --- |
| `get_all_projections_2d()` | Carrega + cache les coordenades pre-calculades, restringides als ids de `load_visible_songs()`. Es loga un warning si el parquet falta i retorna `[]`. |
| `get_visible_song_ids()` | Conjunt d'ids amb projecció 2D. |
| `compute_tsne_2d(songs)` | t-SNE per subconjunts (perplexity dinàmica, `max_iter=500`, `random_state=42`). |
| `compute_neighborhood_2d(songs, focal_id, previous_song_id, previous_positions)` | MDS mètric sobre `1 − cosine(M, M)`, centrat al focal, normalitzat per percentil 75 i Procrustes-aliniat amb les posicions anteriors per donar continuïtat visual entre salts. |
| `invalidate_cache()` | Buida la cache `_cached_all_2d`. |

## Helpers privats

| Nom | Què fa |
| --- | --- |
| `_songs_to_matrix(songs)` | `[s["embedding"] for s in songs] → np.ndarray(n, k)`. |
| `_build_points(songs, coords)` | Combina metadades + `(x, y)` arrodonits a 4 decimals + `role`. |
| `_load_precomputed_2d()` | Lectura del parquet 2D + filtrat per ids visibles. |

## Procrustes per a continuïtat

Quan un usuari salta de cançó A a B i tornen veïns comuns, els seus punts haurien de quedar a prop d'on estaven abans. Es calcula la rotació `R = U Vt` de la SVD de `Aᵀ B` (amb `A` = noves coords del solapament, `B` = antigues coords), s'aplica a `coords`, i els solapaments es **pinquen** exactament a les antigues.
