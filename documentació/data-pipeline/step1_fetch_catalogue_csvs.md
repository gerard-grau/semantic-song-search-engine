# `data_pipeline/step1_fetch_catalogue_csvs.py`

Extreu de MariaDB els 3 CSV catàleg (`cancons.csv`, `grups.csv`, `noticies.csv`) i els escriu a `app/backend/data/raw/`.

## Comportament

- Si els tres CSVs ja existeixen → no-op (log informatiu). `--force` força la refetch.
- Si la connexió falla → warning. Només falla si un CSV obligatori falta i tampoc s'ha pogut baixar.

## Requereix

- `.env` a l'arrel del repo amb `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.

## Funcions

| Nom | Què fa |
| --- | --- |
| `run(force=False)` | Punt d'entrada del step. Llegeix `.env`, decideix si refer cada CSV, dispatcha. |
| `main()` | Wrap d'`argparse` per a `python -m data_pipeline.step1_fetch_catalogue_csvs`. |
| `_db_config()` | Llegeix `.env` i retorna el dict de credencials (o `None` si falta). |
| `_fetch_from_db(cfg)` | Obre la connexió pymysql i dispatcha les 3 queries en cursors `DictCursor`. |
| `_news_rows(cursor)` | SELECT sobre `noticies` + cleaning HTML. |
| `_groups_rows(cursor)` | SELECT sobre `grups` + descripció + foto + ubicació. |
| `_songs_rows(cursor)` | SELECT JOIN per recuperar artista, lletra, àlbum, URL, durada. |
| `_save(rows, path)` | Escriu el CSV en `utf-8` amb la mateixa columna `id_*` que el codi consumeix. |
| `_clean_html(value)` | Decodeix `&entitats;`, treu `<br>`/`<tags>`, espais redundants. |
| `_clean_url(value)` | Concatena base URL si l'enllaç és relatiu. |
| `_build_image_url(directori, fitxer)` | URL pública per foto de grup. |
| `_build_song_link(id_lletra, uri)` | URL pública de la cançó. |
| `_join_unique(values)` | `' | '.join(unique)` per columnes que poden tenir múltiples valors. |
| `_first_non_empty(values)` | Primera entrada no buida d'una llista. |

## Columnes garantides

- `cancons.csv` : `id_lletra, titol, artista, album, durada, lletra, data, viasona_link`.
- `grups.csv`   : `id_grup, nom, num_cancons, descripcio, viasona_link, foto, municipi, regio`.
- `noticies.csv`: `id_article, titol, subtitol, data, entrada, viasona_link`.
