export default function ThemeToggle({ theme, onToggle }) {
  return (
    <button className="theme-toggle" onClick={onToggle} title="Canviar tema">
      {theme === 'light' ? '🌙' : '☀️'}
    </button>
  )
}
