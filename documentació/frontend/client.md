# `app/frontend/src/api/client.js`

Wrappers axios sobre les rutes del backend. Una sola instància d'axios amb `baseURL: '/api'` i `timeout: 120000` (les primeres peticions paguen càrrega del model en cas que el pre-warm fallés).

## Funcions exportades

| Nom | Endpoint | Notes |
| --- | --- | --- |
| `fetchAllSongs()` | `GET /api/songs` | Catàleg visible + projeccions 2D. |
| `filterSongs(query, songIds=null)` | `POST /api/filter` | Filtre per text. |
| `filterSimilarTo(songId, songIds=null)` | `POST /api/filter` | Filtre per similitud cançó-cançó. |
| `fetchSongDetail(songId)` | `GET /api/songs/{id}` | Detall complet. |
| `cercadorSearch(query)` | `GET /api/cercador?q=…` | Cerca lèxica per tecleig. |
| `cercadorSuggestions(query, excludeIds=[], excludeGroups=[], artistFilter=null, mode='all')` | `GET /api/cercador/suggestions` | Suggeriments semàntics. |

## Detalls

- `excludeIds` i `excludeGroups` accepten array o string; es serialitzen com a CSV.
- `artistFilter` només es passa si és truthy.
- `mode` permet provar el fallback per matriu (`mode='matrix'`).
