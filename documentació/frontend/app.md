# `app/frontend/src/App.jsx`

Component arrel. Gestiona l'estat global de l'aplicació: pàgina activa, catàleg complet, projeccions 2D, xips, supervivents, mapa de scores i selecció de gèneres.

## Forma de xip

```js
// chip kinds
{ kind: 'query',   value: string,   label: string }
{ kind: 'similar', value: number,   label: string }   // value = songId
```

Els xips componen progressivament: cada xip estreny el conjunt actiu, independent del seu tipus. Treure un xip torna a executar els restants des de zero.

## Estat principal

| Variable | Significat |
| --- | --- |
| `page` | `'welcome'` \| `'app'` \| `'cercador'` \| `'help'`. |
| `allSongs` | Llista completa retornada per `/api/songs`. |
| `baseProj2d` | Projecció 2D de tot el catàleg. |
| `activeIds` | `null` = sense filtre; altrament `Set<int>` de supervivents. |
| `scoreMap` | `{ id → score }` agregat (mitjana aritmètica dels per-xip). |
| `perChipScoreMaps` | Llista d'objectes `{ id → score }`, un per xip. |
| `chips` | Array dels xips actuals. |
| `selectedGenres` | Slugs seleccionats per la llegenda. |
| `selectedSongId` | Cançó oberta al popup. |

## Funcions clau

| Nom | Què fa |
| --- | --- |
| `addChip(chip)` | Crida l'endpoint adequat (`filterSongs` o `filterSimilarTo`), reduïx amb els xips anteriors i actualitza l'estat. |
| `removeChip(idx)` | Re-executa tots els xips restants des d'`allSongs`. |
| `clearChips()` | Reset complet. |
| `toggleGenre(slug)` | Toggle a `selectedGenres`. Intersecció local sense round-trip. |
| `loadCatalog()` | `fetchAllSongs()` i hidrata `allSongs` + `baseProj2d`. |

## Composició dels scores

El xip simple guarda el `score` per id que retorna `/api/filter`. Combinant múltiples xips, fem la **mitjana aritmètica** dels scores: un id que apareix a `k` xips, té `score = (s1 + s2 + ... + sk) / k`. Així no domina automàticament el xip més recent.
