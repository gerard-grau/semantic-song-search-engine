# `app/frontend/src/components/`

Tots els components React que composen la UI. La majoria reben props i no mantenen estat (l'estat global viu a `App.jsx`).

## Pàgines

| Component | Què fa |
| --- | --- |
| `WelcomePage.jsx` | Landing inicial amb call-to-action cap a la pàgina `'app'`. |
| `HelpPage.jsx` | Explicació del funcionament del scatter, els xips i el cercador. |
| `CercadorPage.jsx` | Pàgina sencera del cercador instantani estil Viasona — input amb debounce, columnes de Grups / Cançons / Notícies, dropdown de suggeriments embedding, "Volies dir...". El component més gran del frontend. |

## Barres i controls

| Component | Què fa |
| --- | --- |
| `FilterBar.jsx` | Combinació de `SearchBar` + render dels xips actius + botó "neteja". |
| `SearchBar.jsx` | Input genèric amb submit per Enter. |
| `ThemeToggle.jsx` | Botó que llança el toggle de `useTheme`. |

## Visualització i resultats

| Component | Què fa |
| --- | --- |
| `visualizations/Scatter2D.jsx` | Renderitzat canvas del scatter, amb zoom/pan, gènere → color (`genreColors.js`), highlight dels supervivents, hover labels i lasso de selecció. |
| `visualizations/genreColors.js` | Mapping `slug → hex`. |
| `TopResults.jsx` | Llista lateral dreta amb els top-K supervivents, ordenats per `scoreMap`. |
| `SongDetail.jsx` | Popup amb `full_lyrics`, enllaç a Viasona, durada. |
| `SongShowcase.jsx` | Targeta d'una cançó destacada. |

## Hook compartit

| Fitxer | Què fa |
| --- | --- |
| `hooks/useTheme.js` | `[theme, toggleTheme]`, persistit a `localStorage`. Aplica una classe al `<html>`. |
