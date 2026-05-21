# `app/backend/core/similarity.py`

Helpers numèrics compartits per `embeddings.py` i `projections.py`. Centralitza la normalització L2 i les matrius de cosinus per no duplicar lògica.

## Funcions

| Nom | Què fa |
| --- | --- |
| `l2_normalize_matrix(matrix)` | Normalitza files perquè cada una tingui norma L2 = 1. Files amb norma 0 es deixen com a zero. |
| `l2_normalize_vector(vec)` | Variant per a un vector. Retorna `vec` tal qual si la norma és 0. |
| `cosine_matrix(matrix)` | Matriu `(n, n)` de cosinus dins d'un conjunt. Equivalent a `M_n @ M_n.T`, clipat a `[-1, 1]`. |
| `cosine_vector(query, matrix)` | Vector `(n,)` de cosinus entre `query` i cada fila. Zeros si la query és nul·la. |

Totes treballen en `float64` i clipen el resultat a `[-1, 1]` per estabilitat numèrica.
