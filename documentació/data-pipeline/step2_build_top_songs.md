# `data_pipeline/step2_build_top_songs.py`

Construeix `top_5000_songs.csv` a partir de l'export GA4 (`entrances_exits.csv`). És l'única ordenació de popularitat que tenen els steps 3, 4 i 5.

## Funcions

| Nom | Què fa |
| --- | --- |
| `run(top_n=5000, force=False)` | Mira si l'output ja existeix, llegeix GA4, filtra files de cançó, talla a `top_n` i hi enganxa la columna `genre` venint de `_genres.RANK_TO_GENRE`. |
| `main()` | Argparse wrap. |
| `_read_ga4(path)` | Llegeix l'export GA4: salta el bloc de capçalera amb `#`, salta files en blanc, llegeix la veritable capçalera. |
| `_filter_songs(df)` | Es queda només amb les files que corresponen a pàgines de cançó (path Viasona conegut), agrupa per `(title, artist)` i suma visites. |

## Columnes de l'output

```
#, song_title, artist, page_title, views, genre
```

`#` és el rank de popularitat (1-based). `genre` ve del diccionari curat manual a `_genres.py` (taxonomia de 9 gèneres).
