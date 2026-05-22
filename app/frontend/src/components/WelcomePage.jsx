import ThemeToggle from './ThemeToggle'

export default function WelcomePage({ onEnter, onCercador, theme, onToggleTheme, isLoading }) {
  return (
    <div className="welcome">
      <div className="welcome-bg" />

      <header className="welcome-topbar">
        <div className="brand-mark">Cançoner</div>
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </header>

      <main className="welcome-content">
        <span className="welcome-eyebrow">Música catalana · cerca semàntica</span>

        <h1 className="welcome-title">
          Troba la cançó<br />
          que <em>encara no</em> coneixes.
        </h1>

        <p className="welcome-desc">
          Explora milers de cançons catalanes a través del seu significat.
          Escriu el que sents, descobreix-ne de noves o navega pel mapa
          d'embeddings com qui passeja per una constel·lació.
        </p>

        <div className="welcome-choices">
          <button
            className="choice-card"
            onClick={onCercador}
            type="button"
          >
            <div className="choice-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
            </div>
            <div className="choice-title">Cercador</div>
            <div className="choice-desc">
              Cerca per nom de grup, lletra, títol o notícia.
              Resultats instantanis amb correcció ortogràfica.
            </div>
            <span className="choice-arrow">
              Obrir el cercador
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </span>
          </button>

          <button
            className="choice-card choice-card--primary"
            onClick={onEnter}
            disabled={isLoading}
            type="button"
          >
            <div className="choice-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="6" cy="6" r="2" />
                <circle cx="18" cy="9" r="2" />
                <circle cx="9" cy="17" r="2" />
                <circle cx="19" cy="18" r="1.5" />
                <path d="M8 7l8 1M8 16l9 1M11 16l6-6" opacity="0.5" />
              </svg>
            </div>
            <div className="choice-title">Descobridor</div>
            <div className="choice-desc">
              Mapa visual de cançons agrupades pel seu significat.
              Filtra amb llenguatge natural i navega per similitud.
            </div>
            <span className="choice-arrow">
              {isLoading ? 'Carregant…' : 'Entrar al mapa'}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </span>
          </button>
        </div>
      </main>

      <footer className="welcome-foot">
        <span className="welcome-foot-line">
          <span>Dades de</span>
          <a
            className="viasona-credit"
            href="https://www.viasona.cat"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="viasona.cat"
          >
            <img src="/viasona-logo.png" alt="Viasona" />
          </a>
          <span aria-hidden="true">·</span>
          <span>Embeddings: sentence-transformers</span>
        </span>
      </footer>
    </div>
  )
}
