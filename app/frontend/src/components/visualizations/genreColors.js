// 6-label taxonomy — keep in sync with data_pipeline/_genres.py::GENRES.
// Hue spacing chosen so adjacent buckets stay distinguishable in the scatter.
export const GENRE_COLORS = {
  'folk':          '#4FC3F7', // sky blue
  'cançó autor':   '#7E57C2', // violet
  'pop-rock':      '#00BFA5', // teal
  'rumba':         '#FF8A65', // warm orange
  'havanera':      '#26A69A', // sea green
  'música urbana': '#FFB74D', // mango
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
