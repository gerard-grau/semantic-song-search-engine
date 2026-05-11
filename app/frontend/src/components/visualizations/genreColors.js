export const GENRE_COLORS = {
  pop:           '#FF6B6B',
  rock:          '#00BFA5',
  folk:          '#4FC3F7',
  electronica:   '#AB47BC',
  'hip-hop':     '#FFB74D',
  rumba:         '#FF8A65',
  'cançó-autor': '#81C784',
  punk:          '#E57373',
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
