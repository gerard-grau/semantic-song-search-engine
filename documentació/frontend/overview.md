# `app/frontend/` — visió general

SPA en **React 19 + Vite 8**. Tot el codi viu sota `app/frontend/src/`.

## Comandes

```bash
cd app/frontend
npm install
npm run dev      # arrenca Vite a http://localhost:5173 amb proxy /api → backend
npm run build    # bundle de producció a app/frontend/dist/
npm run preview  # serveix el bundle estàtic
```

El proxy `/api` està configurat a `vite.config.js` apuntant a `http://localhost:8000` (el backend FastAPI).

## Estructura

```
app/frontend/
├── index.html               — HTML d'entrada
├── package.json             — react, react-dom, axios, vite, eslint
├── vite.config.js           — plugin react + proxy /api
├── public/                  — assets servits literals (favicon, icons.svg)
└── src/
    ├── main.jsx             — mount React
    ├── App.jsx              — orquestrador global (chips, scatter, panells)
    ├── App.css              — estils globals
    ├── index.css            — reset / fonts
    ├── hooks/
    │   └── useTheme.js      — toggle dark/light persistent
    ├── api/
    │   └── client.js        — wrappers axios per a totes les rutes
    └── components/
        ├── WelcomePage.jsx        — landing
        ├── HelpPage.jsx           — ajuda
        ├── CercadorPage.jsx       — pàgina cercador (gran, estil Viasona)
        ├── FilterBar.jsx          — barra de cerca per al scatter
        ├── SearchBar.jsx          — input genèric
        ├── SongDetail.jsx         — popup amb full_lyrics
        ├── SongShowcase.jsx       — destacat
        ├── TopResults.jsx         — llista a la dreta del scatter
        ├── ThemeToggle.jsx        — botó tema
        └── visualizations/
            ├── Scatter2D.jsx      — scatter principal en canvas
            └── genreColors.js     — paleta per gènere
```

## Components per fitxer

| Fitxer | Doc |
| --- | --- |
| `App.jsx` | [app.md](app.md) |
| `api/client.js` | [client.md](client.md) |
| `components/*.jsx`, `visualizations/*` | [components.md](components.md) |
