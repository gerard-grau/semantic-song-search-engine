import ThemeToggle from './ThemeToggle'

export default function WelcomePage({ onEnter, onCercador, theme, onToggleTheme, isLoading }) {
  return (
    <div className="welcome">
      <ThemeToggle theme={theme} onToggle={onToggleTheme} />

      <div className="welcome-content">
        <h1 className="welcome-title">Descobridor de Cançons</h1>
        <p className="welcome-desc">
          Explora un univers de cançons catalanes a través de cerques semàntiques.
          Escriu el que sents i descobrirem les cançons que millor s'hi acosten.
          Cada cerca filtra i refina els resultats fins trobar la teva cançó.
        </p>
        <div className="welcome-buttons">
          <button className="welcome-btn" onClick={onEnter} disabled={isLoading}>
            {isLoading ? 'Carregant…' : 'Descobreix Viasona'}
          </button>
          <button className="welcome-btn welcome-btn--secondary" onClick={onCercador}>
            Cerca Viasona
          </button>
        </div>
      </div>

      <div className="welcome-bg" />
    </div>
  )
}
