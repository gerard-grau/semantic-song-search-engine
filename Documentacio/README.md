# Documentació — Semantic Song Search Engine

Aquesta carpeta conté la documentació tècnica completa del projecte, organitzada
per àrees. La documentació s'escriu en **català** i es manté sincronitzada amb
el codi del repositori.

## Mapa de la documentació

| Document | Què cobreix |
| --- | --- |
| [`01_visio_general.md`](01_visio_general.md) | Què fa el projecte, casos d'ús, components d'alt nivell, flux de dades. |
| [`02_arquitectura.md`](02_arquitectura.md) | Diagrama de capes, contractes entre mòduls, dependències. |
| [`03_backend.md`](03_backend.md) | Referència fitxer-a-fitxer i funció-a-funció del backend FastAPI. |
| [`04_frontend.md`](04_frontend.md) | Referència de tots els components React, hooks, client d'API i visualitzacions. |
| [`05_searchoptimal.md`](05_searchoptimal.md) | Parser de cerca tipus "Did you mean / autocomplete" en català. |
| [`06_etl_i_dades.md`](06_etl_i_dades.md) | Extracció i transformació de la BD Viasona, format dels CSV/parquet. |
| [`07_pipeline_youtube.md`](07_pipeline_youtube.md) | Pipeline d'extracció de característiques d'àudio de YouTube. |
| [`08_api_reference.md`](08_api_reference.md) | Referència completa dels endpoints HTTP. |
| [`09_desplegament.md`](09_desplegament.md) | Com instal·lar, executar i depurar localment. |
| [`10_codi_mort_i_millores.md`](10_codi_mort_i_millores.md) | Codi obsolet detectat, suggeriments futurs i criteris de neteja. |

## Convencions

- **"Cançó"** = entrada del catàleg amb `id`, `title`, `artist`, `embedding`, etc.
- **"Embedding"** = vector dens (per defecte 384 dimensions) generat per
  `intfloat/multilingual-e5-small` a partir de la lletra i metadades.
- **"Filtratge progressiu"** = cada cerca redueix el conjunt actiu de cançons
  per similitud cosinus, no es ressalta tot el catàleg sinó que es restringeix.
- **"Cercador"** = pestanya tipus Google instant search (`/cercador`) sobre
  grups + cançons + notícies, separada del cercador semàntic (`/api/filter`).

## Dependències del codi

```
React (frontend)  ──HTTP/JSON──▶  FastAPI (backend)
                                       │
                                       ├─▶ data_loader  ──▶ parquet + CSV
                                       ├─▶ encoder       ──▶ HuggingFace transformers
                                       ├─▶ embeddings    ──▶ similarity (numpy)
                                       ├─▶ projections   ──▶ scikit-learn t-SNE/MDS
                                       └─▶ searchoptimal/parser  (cerca instant)

ETL (offline):
   MariaDB Viasona  ──▶ data_getter.py  ──▶ noticies.csv / grups.csv / cancons.csv
   cancons.csv      ──▶ ml/embeddings/preembedding.py  ──▶ embedded_songs.parquet
   embedded_songs   ──▶ data_pipeline.py                ──▶ embedded_songs_2d.parquet
```
