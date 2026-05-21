# `data_pipeline/execute_all.py`

Punt d'entrada únic. Encadena els 6 steps en ordre i loga el temps de cada un.

## Comandes

```bash
# Idempotent: només refà el que faltava.
python -m data_pipeline.execute_all

# Refà tot des de zero.
python -m data_pipeline.execute_all --force

# Sobreescriu els paràmetres de la projecció 2D.
python -m data_pipeline.execute_all --method tsne --alpha-genre 3.0
```

## Flags

| Flag | Valor per defecte (config.py) | Significat |
| --- | --- | --- |
| `--force` | False | Reconstrueix cada output encara que ja existeixi. |
| `--method` | `PIPELINE_PROJECTION_METHOD` (`"umap"`) | Backend de projecció 2D: `umap` / `tsne` / `pca_umap`. |
| `--pca-dim` | `PIPELINE_PCA_DIM` (`50`) | Pre-reducció PCA abans de t-SNE / pca_umap (0 desactiva). |
| `--genre-mode` | `PIPELINE_GENRE_MODE` (`"soft"`) | Com participa el bloc de gèneres a la projecció: `soft` / `onehot` / `none`. |
| `--alpha-genre` | `PIPELINE_ALPHA_GENRE` (`0.2`) | Pes del bloc de gèneres a la distància quadrada. |

## Steps encadenats

| Etapa | Mòdul | Output |
| --- | --- | --- |
| 1 | `step1_fetch_catalogue_csvs` | `cancons.csv`, `grups.csv`, `noticies.csv` a `raw/`. |
| 2 | `step2_build_top_songs` | `processed/top_5000_songs.csv` (amb columna `genre`). |
| 3 | `step3_filter_top5000_embeddings` | `processed/embedded_songs_top5000.parquet`. |
| 4 | `step4_build_genres_parquet` | `processed/embedded_songs_genres.parquet`. |
| 5 | `step5_build_meta` | `processed/songs_meta.parquet`. |
| 6 | `step6_project_2d` | `processed/embedded_songs_2d.parquet`. |

Cada step és idempotent: comprova si l'output ja existeix i es salta si no s'ha passat `--force`.
