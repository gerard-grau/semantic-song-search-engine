// 11-label taxonomy — keep in sync with etl/build_artist_genres.py::GENRES.
// Hue spacing chosen so adjacent buckets stay distinguishable in the scatter.
export const GENRE_COLORS = {
  pop:         '#FF6B6B', // coral red
  rock:        '#00BFA5', // teal
  indie:       '#7E57C2', // violet
  folk:        '#4FC3F7', // sky blue
  rumba:       '#FF8A65', // warm orange
  ska:         '#FFD54F', // amber yellow
  punk:        '#E53935', // crimson
  'hip-hop':   '#FFB74D', // mango
  electronica: '#AB47BC', // magenta
  havaneres:   '#26A69A', // sea green
  infantil:    '#81C784', // mint green
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
