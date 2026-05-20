// 9-label taxonomy — keep in sync with data_pipeline/_genres.py::GENRES.
// Hue spacing chosen so adjacent buckets stay distinguishable in the scatter.
export const GENRE_COLORS = {
  "cançó d'autor": '#7E57C2', // violet — singer-songwriter tradition
  'folk':          '#4FC3F7', // sky blue — modern folk-revival
  'tradicional':   '#26A69A', // sea green — sardanes/havaneres/popular
  'rock':          '#E53935', // crimson — Rock Català
  'pop':           '#00BFA5', // teal — indie-pop / pop-folk
  'rumba':         '#FF8A65', // warm orange — rumba catalana
  'música urbana': '#FFB74D', // mango — hip-hop / trap / urbano
  'infantil':      '#FFEB3B', // yellow — children's music
  'mestissa':      '#66BB6A', // green — ska / reggae / cumbia fusion
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
