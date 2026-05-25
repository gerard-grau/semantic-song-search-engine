// 9-label taxonomy — the label SET must stay in sync with
// data_pipeline/_genres.py::GENRES (colours and order here are display-only).
// Key order = how the genre clusters read left→right across the 2D scatter
// (by mean projection x), so the legend lines up with the map. This is
// deliberately NOT the backend GENRES order. Hues stay mutually
// distinguishable; lookups are by key, so reordering is purely cosmetic.
export const GENRE_COLORS = {
  'pop':           '#00BFA5', // teal — indie-pop / pop-folk
  'música urbana': '#FFB74D', // mango — hip-hop / trap / urbano
  'infantil':      '#F53DD6', // vivid pink-lilac — children's music (yellow was illegible)
  'rock':          '#E53935', // crimson — Rock Català
  'rumba':         '#FF8A65', // warm orange — rumba catalana
  'mestissa':      '#66BB6A', // green — ska / reggae / cumbia fusion
  "cançó d'autor": '#7E57C2', // violet — singer-songwriter tradition
  'folk':          '#4FC3F7', // sky blue — modern folk-revival
  'tradicional':   '#26A69A', // sea green — sardanes/havaneres/popular
}

export const DEFAULT_COLOR = '#888'

export function genreColor(genre) {
  return GENRE_COLORS[genre] || DEFAULT_COLOR
}

export function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return [r, g, b]
}
