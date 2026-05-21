# `app/backend/api/routes/cercador.py`

Rutes del "Cercador instantani" estil Viasona — cerca lèxica + suggeriments semàntics.

## Endpoints

### `GET /api/cercador?q=…`

Cerca lèxica per tecleig viu. Crida `CercadorIndex.search(q)` (índex invertit sobre `cancons`/`grups`/`noticies`) i `derive_correction(...)` per generar el "Volies dir...".

Forma de resposta:
```json
{
  "grups":      [ { id, name, song_count, viasona_link, foto, municipi, regio, genres } ],
  "cancons":    [ { id, title, artist, lyrics_snippet, genre, url } ],
  "noticies":   [ { id, title, snippet, date, viasona_link } ],
  "correction": null | { "corrected": "...", "suggestions": [...] }
}
```

### `GET /api/cercador/suggestions?q=…`

Cerca semàntica complementària amb el model bge-m3 i Qdrant. S'invoca per separat des del frontend (idle/perl/per espai) per no pagar el cost del model a cada tecla.

Params:
- `q` — query.
- `exclude_ids`, `exclude_groups` — ids/noms que ja apareixen a la columna lèxica, per evitar duplicats.
- `artist_filter` — restringeix Qdrant a un sol artista.
- `mode` — `"all"` (default), `"lyrics"`, `"qualitative"`, `"title"`, `"matrix"` (força el fallback per matriu).

Resposta:
```json
{
  "suggestions":  [ { id, title, artist, lyrics_snippet, genre, url, score } ],
  "lyrics_extra": [ { ... } ],
  "group_extra":  [ { ...grup..., score } ]
}
```

## Helpers privats

| Nom | Què fa |
| --- | --- |
| `_song_result(song)` / `_grup_result(grup)` / `_noticia_result(n)` | Mapatges de `dict` a la forma de resposta. |
| `_suggestion_result(song, score)` | Empaqueta un suggeriment amb el `score` clampejat a `[0,1]`. |
| `_parse_exclude_ids(raw)` | `"1,2,3"` → `{1, 2, 3}`. |
| `_parse_exclude_names(raw)` | `"Manel,Sopa de Cabra"` → `{"Manel", "Sopa de Cabra"}`. |
| `_qdrant_suggestions(...)` | Camí Qdrant: codifica `q`, llança qualitative + lyrics chunks + title (segons `mode`), enriqueix amb metadades i calcula `group_extra` amb una matmul a la columna `embedded_artist`. |
| `_matrix_suggestions(...)` | Fallback per matriu: si Qdrant no està disponible, fa servir `compute_cercador_suggestions(...)` sobre l'índex visible (top-5000). |
| `_build_group_extra(name, score)` | Combina un nom d'artista amb el seu registre de `grups.csv` (via `find_grup_by_name`). |

## Comportament en mode degradat

Si Qdrant no respon (no està engegat o sense col·leccions): l'endpoint retorna automàticament la versió matriu (`_matrix_suggestions`), limitada a 5000 cançons. No es propaguen excepcions a l'usuari.
