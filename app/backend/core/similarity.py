"""
Helpers compartits de similitud cosinus.

Centralitza la normalització L2 i el càlcul de matrius de cosinus per
evitar que la mateixa lògica visqui repetida a `embeddings.py` i
`projections.py`. La precisió i el comportament numèric són exactament
els mateixos que els de les implementacions originals (clip [-1, 1],
norma 0 → 1.0 per evitar divisions per zero).
"""

from __future__ import annotations

import numpy as np


def l2_normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    """
    Normalitza les files de `matrix` perquè cadascuna tingui norma L2 = 1.

    Files amb norma 0 es deixen tal qual (es divideixen per 1.0) per
    evitar NaN; el resultat és el vector zero, amb similitud 0 amb
    qualsevol altre vector.
    """
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return matrix / norms


def l2_normalize_vector(vec: np.ndarray) -> np.ndarray:
    """Variant per a un únic vector. Retorna el vector zero si la norma és 0."""
    n = float(np.linalg.norm(vec))
    if n == 0.0:
        return vec
    return vec / n


def cosine_matrix(matrix: np.ndarray) -> np.ndarray:
    """
    Matriu (n, n) de similituds cosinus per a un conjunt de vectors fila.

    Equivalent a `(M_normed @ M_normed.T)` amb les similituds retallades
    a [-1, 1] per estabilitat numèrica.
    """
    normed = l2_normalize_matrix(matrix.astype(np.float64, copy=False))
    return np.clip(normed @ normed.T, -1.0, 1.0)


def cosine_vector(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """
    Vector (n,) de similituds cosinus entre `query` i cada fila de `matrix`.

    Si `query` té norma 0 retorna un vector de zeros — comportament que
    coincideix amb el codi original a `embeddings.filter_embeddings`.
    """
    q = l2_normalize_vector(query.astype(np.float64, copy=False))
    if not np.any(q):
        return np.zeros(matrix.shape[0], dtype=np.float64)
    M = l2_normalize_matrix(matrix.astype(np.float64, copy=False))
    return np.clip(M @ q, -1.0, 1.0)
