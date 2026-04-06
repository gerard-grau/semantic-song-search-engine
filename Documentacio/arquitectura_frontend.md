# Arquitectura del Frontend

## Tecnologies

- **React 19** amb Vite 8 com a bundler
- **deck.gl** per visualitzacions 2D i navegació 2D (buildings)
- **@react-three/fiber + drei** per visualitzacions 3D i navegació 3D (sistema solar)
- **axios** per crides HTTP al backend

## Estructura de fitxers

```
app/frontend/src/
├── main.jsx                        # Entry point, munta <App /> al DOM
├── App.jsx                         # Component principal, gestió d'estat global
├── App.css                         # Tots els estils (amb CSS variables per temes)
├── index.css                       # Reset CSS + definició de temes light/dark
├── api/
│   └── client.js                   # Funcions per comunicar amb el backend
├── hooks/
│   └── useTheme.js                 # Hook per gestió de tema light/dark
└── components/
    ├── WelcomePage.jsx             # Pàgina de benvinguda
    ├── SearchBar.jsx               # Barra de cerca + botons
    ├── TopResults.jsx              # Llista dels top 10 resultats
    ├── SongDetail.jsx              # Popup modal amb detalls de la cançó
    ├── ThemeToggle.jsx             # Botó sol/lluna per canviar tema
    ├── VizSelector.jsx             # Selector dels 4 modes de visualització
    └── visualizations/
        ├── genreColors.js          # Mapa de colors per gènere (compartit)
        ├── Scatter2D.jsx           # deck.gl ScatterplotLayer + OrthographicView
        ├── Scatter3D.jsx           # deck.gl ScatterplotLayer + OrbitView
        ├── Navigation2D.jsx        # deck.gl ColumnLayer (edificis)
        └── Navigation3D.jsx        # Three.js esferes + Stars (sistema solar)
```

## Flux de dades

```
App.jsx (estat global)
  │
  ├── WelcomePage ← onEnter() → crida GET /api/songs → canvia a pàgina principal
  │
  ├── SearchBar ← onSearch(query) → crida POST /api/filter → actualitza estat
  │              ← onReset() → crida GET /api/songs → restaura estat inicial
  │
  ├── TopResults ← rep songs[], message, query
  │              → onSongHover(id) → actualitza highlightedId
  │              → onSongClick(id) → obre SongDetail popup
  │
  ├── Visualization (Scatter2D | Scatter3D | Navigation2D | Navigation3D)
  │   ← rep points[], highlightedId, topIds[], faded, scores[]
  │   → onPointHover(id) → actualitza highlightedId
  │   → onPointClick(id) → obre SongDetail popup
  │
  └── SongDetail ← songId → crida GET /api/songs/{id}
                 → onClose() → tanca el popup
```

## Sistema de temes

El tema es gestiona amb CSS custom properties definides a `index.css`:

```css
:root, [data-theme="light"] { --bg-primary: #FAF8F5; --accent: #D35400; ... }
[data-theme="dark"]          { --bg-primary: #111118; --accent: #7C6AEF; ... }
```

El hook `useTheme()`:
1. Llegeix el tema de `localStorage` (o 'light' per defecte)
2. Aplica `data-theme` a `<html>` via `document.documentElement.setAttribute`
3. Retorna `{ theme, toggleTheme }` per al component ThemeToggle

El tema light està inspirat en la paleta càlida de Viasona (taronges, blancs cremosos). El tema dark utilitza violetes foscos.

## Estat de l'aplicació (App.jsx)

| Variable | Tipus | Descripció |
|---|---|---|
| `page` | `'welcome' \| 'main'` | Pàgina actual |
| `allSongs` | `Song[]` | Totes les cançons (per al reset) |
| `songs` | `Song[]` | Cançons actuals (filtrades) |
| `songIds` | `int[] \| null` | IDs de cançons vives (`null` = totes) |
| `proj2d` / `proj3d` | `Point[]` | Projeccions t-SNE actuals |
| `query` | `string` | Última consulta |
| `message` | `string \| null` | Missatge de l'API (ex: "Explora les 3 cançons per tu") |
| `vizMode` | `'2D' \| '3D' \| 'nav2D' \| 'nav3D'` | Mode de visualització |
| `selectedSongId` | `int \| null` | Cançó seleccionada per al popup |
| `highlightedId` | `int \| null` | Cançó ressaltada per hover |

## Proxy de desenvolupament

El `vite.config.js` configura un proxy perquè `/api/*` vagi directament al backend a `http://127.0.0.1:8000`. Això evita problemes de CORS durant el desenvolupament.
