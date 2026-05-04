# 04 — Frontend: referència de components

Tots els camins són relatius a `app/frontend/src/`. L'aplicació és una SPA
amb React 19 i Vite. No hi ha router — la navegació entre la pàgina
"welcome", la principal i el cercador es fa amb un únic state `page` a `App.jsx`.

## Estructura

```
src/
├── main.jsx                  ← punt d'entrada (createRoot + StrictMode)
├── App.jsx                   ← state global + orquestració
├── index.css / App.css       ← estils globals
├── api/client.js             ← totes les crides axios al backend
├── hooks/useTheme.js         ← persistent light/dark theme
└── components/
    ├── WelcomePage.jsx
    ├── CercadorPage.jsx
    ├── ThemeToggle.jsx
    ├── FilterBar.jsx
    ├── TopResults.jsx
    ├── VizSelector.jsx
    ├── SongDetail.jsx
    └── visualizations/
        ├── Scatter2D.jsx
        ├── Scatter3D.jsx
        ├── Navigation2D.jsx
        └── genreColors.js
```

> **Components no utilitzats (codi mort):** `SearchBar.jsx`, `SongShowcase.jsx`.
> No s'importen des d'enlloc dins l'arbre de components actiu. Veure
> [`10_codi_mort_i_millores.md`](10_codi_mort_i_millores.md).

---

## `main.jsx`

`createRoot` + `StrictMode` + `App`. Sense providers globals; tot el state
viu a dins d'`App`.

## `App.jsx`

Orquestrador principal. Manté l'estat global de l'aplicació amb hooks. No usa
context.

### Estats principals

| State | Significat |
| --- | --- |
| `page` | `'welcome'` \| `'main'` \| `'cercador'` |
| `allSongs`, `baseProj2d`, `baseProj3d` | Dataset complet i les seves projeccions; **constants per sessió** un cop carregats. |
| `activeIds` (`Set` o `null`) | Cançons "actives" actualment. `null` = totes. |
| `scoreMap` | `{songId → score 0..1}` per redimensionar i ordenar. |
| `chips` | Llista de queries acumulades a la barra de filtre (mode progressiu). |
| `similarToId` / `similarToTitle` | Mode d'exploració per veïns (clic sobre un punt). |
| `vizMode` | `'2D'` \| `'3D'` \| `'nav'` |
| `selectedSongId` | Si != null, mostra `SongDetail` (modal). |
| `highlightedId` | Hover compartit entre llista i visualització. |
| `aliveIdsRef` | Ref amb la llista d'ids alive (per encadenar `/api/filter`). |

### Handlers clau

- `loadAll()` — `GET /api/songs`, omple `allSongs` + projeccions, reseteja la
  resta. S'invoca quan es prem "Descobreix Viasona" des del welcome o quan
  es vol fer un reset complet.
- `handleAddChip(q)` — `POST /api/filter` amb la llista actual `aliveIdsRef`
  com a `song_ids`. Acumula la query a `chips`.
- `handleRemoveChip(i)` — re-aplica seqüencialment totes les chips restants
  des de zero (no hi ha cache parcial).
- `handleReset()` — neteja state local sense recarregar (la càrrega inicial
  ja es manté).
- `handleSongExplore(songId)` — `POST /api/neighbors`, intersectant amb les
  ids actives si hi ha chip filters.
- `handleExitSimilar()` — torna a l'estat amb chips actius o reset complet.
- `handleOpenDetail(songId)` — obre el modal.

### Render

Header + `error-banner` + `<main>` amb dos panells:
- **panel-left**: `TopResults`.
- **panel-right**: `FilterBar` → `VizSelector` + comptador → barra "exploració
  similar" si `similarToId` → `Scatter2D` / `Scatter3D` / `Navigation2D`.

`SongDetail` viu fora del `<main>` perquè és un modal full-screen.

---

## `api/client.js`

Capa fina sobre axios. Tots els endpoints en un sol fitxer:

```js
fetchAllSongs()                     → GET    /api/songs
filterSongs(query, songIds=null)    → POST   /api/filter
fetchSongDetail(songId)             → GET    /api/songs/{id}
cercadorSearch(query)               → GET    /api/cercador?q=...
fetchNeighbors(songId, options)     → POST   /api/neighbors
```

`baseURL: '/api'` perquè Vite fa proxy a `127.0.0.1:8000` (vegeu
`vite.config.js`). `timeout: 120000 ms` — generós per absorbir la primera
crida després d'arrencar el backend mentre carrega el model.

---

## `hooks/useTheme.js`

Hook simple per al tema light/dark. Persisteix a `localStorage` i fixa un
atribut `data-theme="..."` a `<html>` perquè els selectors CSS condicionin
els estils. Retorna `{ theme, toggleTheme }`.

---

## `components/WelcomePage.jsx`

Splash inicial. Botons:
- "Descobreix Viasona" → `onEnter` (càrrega + entra a la SPA principal).
- "Cerca Viasona" → `onCercador` (canvia a la pestanya cercador).

## `components/ThemeToggle.jsx`

Botó 🌙/☀️. Pur, sense state propi.

## `components/FilterBar.jsx`

Form que mostra les chips acumulades + un input lliure + botó "Filtrar" + (si
hi ha chips) botó "Reset". Notifica via callbacks `onAddChip(q)`,
`onRemoveChip(i)`, `onReset()`.

## `components/TopResults.jsx`

Llista de resultats al panell esquerre. Implementa paginació local (10 visibles
inicialment, "Veure'n més" afegeix 10 més). Cada targeta té rank, títol,
gènere (badge), artista, metadata (album · any), snippet de lletra, i si hi ha
`query`, una barra vertical de score (0-100 %).

Esdeveniments:
- `onMouseEnter`/`onMouseLeave` → `onSongHover(id|null)`.
- `onClick` → `onSongClick(id)`.

## `components/VizSelector.jsx`

Conjunt de tres botons que canvien `vizMode`. Etiquetes: "Dispersió 2D",
"Dispersió 3D", "Navegació".

## `components/SongDetail.jsx`

Modal full-screen amb backdrop. Crida `fetchSongDetail` quan canvia `songId`.
Mostra títol, artista, gènere (badge), àlbum, any, durada, idioma, lletra
completa (`<pre>`) i enllaç extern a Viasona. Tanca per backdrop o "✕".

## `components/CercadorPage.jsx`

Pestanya tipus instant search. Té un input amb debouncing de 150 ms; cada
keystroke després del debounce dispara `cercadorSearch(q)`.

### Helper `highlightText(text, terms)`

Embolica les coincidències en `<mark className="cerca-highlight">`. Filtra
termes < 2 caràcters per soroll. Construeix una sola regex amb tots els termes
escapats. **Es ressalta tant la query original com la corregida** — així
quan l'usuari escriu "buos", encara es marca la "u" en "Buhos" (el corregit).

### Renderitzat

Mostra fins a tres seccions: GRUPS (esquerra), LLETRES + NOTÍCIES (dreta).
La columna dreta s'oculta si no hi ha resultats; igual amb l'esquerra. Si
n'hi ha de tots dos costats, s'usa layout en 2 columnes.

Si la resposta porta `correction`, es mostra una banda "Volies dir: …" amb
botons clicables que substitueixen la query.

---

## `components/visualizations/`

### `genreColors.js`

Mapa centralitzat `genre → color hex` + helper `genreColor(genre)` (fallback
gris) + `hexToRgb(hex)` (per als deck.gl/three layers que volen RGB).

### `Scatter2D.jsx`

Canvas 2D pur (sense React per dibuixar — escriu directament al `2dContext`).
Implementa pan/zoom amb mouse, double-click → detall, click simple → veïns.

Hovers i focal es renderitzen en quatre passades:
1. Cançons inactives dimmed (si hi ha filtre).
2. Cançons actives.
3. Focal (rombe + label més gran).
4. Cançó hovered (anell de glow + halo + label).

`pointToScreen` aplica una `baseTransform` (scale + offset per encabir
totes les cançons) i una `viewTransform` (`panX, panY, zoom`).

`findClosestPoint(mx, my)` itera tots els punts. Per a 5-10k cançons és
suficient ràpid sobre el canvas amb buffer DPR; si el catàleg creix
significativament caldria un quad-tree o spatial index.

### `Scatter3D.jsx`

`@react-three/fiber` Canvas amb `OrbitControls`. Càmera situada en funció del
rang dels punts. Cada cançó és un `SongSphere` (component intern) amb
`Html` per al tooltip.

### `Navigation2D.jsx`

Visualització de tipus "ciutat": cada cançó és un edifici a una graella, i
l'alçada és proporcional al score (després d'una cerca) o a un hash de l'id
(abans d'una cerca, decoratiu).

`snapToGrid(points, gridSize)`:
1. Normalitza coordenades t-SNE a una graella `gridSize × gridSize`.
2. Si una cel·la ja està ocupada, fa una cerca espiral fins a trobar-ne una
   lliure (resol col·lisions).

`Building` rendaritza una caixa coloreada pel gènere amb un tooltip al hover.
`Ground` és un pla translúcid; `GridLines` un `THREE.GridHelper`.
