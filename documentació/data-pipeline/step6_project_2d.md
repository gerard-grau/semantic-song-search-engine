# `data_pipeline/step6_project_2d.py`

Calcula la projecció 2D del top 5000 i escriu `embedded_songs_2d.parquet` amb columnes `id_lyrics, x, y`.

## Augmentació amb gèneres

El vector de layout no és només el text:

```
layout[i] = concat( unit(text[i]), alpha_genre · unit(genre_block[i]) )
```

Amb les dues meitats unit-norm per fila, `alpha_genre` controla directament la influència del gènere a la distància (contribució exacta `alpha_genre² × text`). Valor per defecte `0.2` per no eclipsar la semàntica dins de gènere.

## Funcions

| Nom | Què fa |
| --- | --- |
| `run(method, pca_dim, genre_mode, alpha_genre, force)` | Pipeline complet. |
| `main()` | Argparse wrap. |
| `_load_embeddings(source)` | Llegeix el parquet top5000 i extreu `embedded_lyrics` a `np.ndarray(N, D)`. |
| `_load_genre_block(ids, mode)` | Carrega `embedded_songs_genres.parquet`: `soft` retorna el softmax, `onehot` el argmax-one-hot, `none` desactiva. |
| `_prepare(text, genre_block, alpha)` | Aplica `_row_normalize` a cada meitat i les concatena. |
| `_umap(matrix, metric)`, `_tsne(matrix)` | Backends concrets. |
| `_project(matrix, method, augmented)` | Despatxa segons `method ∈ {umap, tsne, pca_umap}`. |
| `_row_normalize(matrix)` | L2 row-wise. |
| `_emb_to_array(val)` | Parsing tolerant d'una cel·la d'embedding (igual que a `data_loader.py`). |
