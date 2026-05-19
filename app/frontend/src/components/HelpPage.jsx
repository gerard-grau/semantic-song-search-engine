import { useEffect } from 'react'
import { GENRE_COLORS } from './visualizations/genreColors'

/**
 * Full-screen help overlay. Walks the user through every interactive
 * feature of the Descobridor (and the Cercador) with small, on-brand
 * illustrations built from the same component primitives the real app
 * uses, so what they see here matches what they get.
 */
export default function HelpPage({ onClose }) {
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  return (
    <div className="help-page" role="dialog" aria-label="Ajuda i guia">
      <div className="help-bg" aria-hidden="true" />

      <header className="help-topbar">
        <button className="help-back" onClick={onClose} type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Tornar
        </button>
        <span className="help-eyebrow">Guia · Què pots fer</span>
      </header>

      <main className="help-content">
        <section className="help-hero">
          <h1 className="help-title">
            Una <em>guia visual</em> del Descobridor.
          </h1>
          <p className="help-lede">
            Tot el que pots fer al mapa, explicat amb il·lustracions. Cap
            menú amagat: si veus alguna cosa, és clicable.
          </p>
        </section>

        <FeatureCard
          number="01"
          title="Filtres composables"
          subtitle="Cada filtre redueix els resultats anteriors"
        >
          <p>
            Escriu una cerca i prem <Kbd>Enter</Kbd>: apareix un{' '}
            <em>chip</em>. Escriu-ne un altre i s'afegeix; la llista de cançons
            i el mapa s'intersequen. Pots treure qualsevol chip clicant{' '}
            <Kbd>×</Kbd> i la cerca es recalcula amb la resta.
          </p>
          <Illustration label="Quan cliques 'Filtrar', el nou chip s'afegeix; el comptador baixa.">
            <div className="mock-filterbar">
              <span className="mock-chip">amor <Cross /></span>
              <span className="mock-chip">tristesa <Cross /></span>
              <span className="mock-chip mock-chip--similar">≈ similars a "Boig per tu" <Cross /></span>
              <span className="mock-input">Afegeix un altre filtre...</span>
              <span className="mock-btn mock-btn--primary">Filtrar</span>
            </div>
            <div className="mock-count">
              <strong>312</strong> / 5000 cançons supervivents
            </div>
          </Illustration>
        </FeatureCard>

        <FeatureCard
          number="02"
          title="Filtra per gènere"
          subtitle="La llegenda del mapa també és un filtre"
        >
          <p>
            Clica un gènere a la llegenda i només quedaran cançons d'aquell
            gènere. Un <strong>clic simple</strong> selecciona només aquest;{' '}
            <Kbd>Ctrl</Kbd>/<Kbd>⌘</Kbd>-clic n'afegeix més d'un. No genera
            cap chip: la selecció es mostra a la pròpia llegenda
            (l'element activat es ressalta).
          </p>
          <Illustration label="Selecció múltiple amb Ctrl/⌘-clic.">
            <div className="mock-legend">
              {Object.entries(GENRE_COLORS).map(([g, c], i) => {
                const active = i === 1 || i === 3
                return (
                  <span
                    key={g}
                    className={'mock-legend-item' + (active ? ' mock-legend-item--active' : '')}
                    style={active ? { background: c } : { '--legend-color': c }}
                  >
                    <span className="mock-legend-dot" style={{ background: c }} />
                    {g}
                  </span>
                )
              })}
            </div>
          </Illustration>
        </FeatureCard>

        <FeatureCard
          number="03"
          title="Punt → cançó → similars"
          subtitle="Cada punt del mapa és clicable"
        >
          <p>
            Passa el cursor pel mapa: els punts clicables es marquen amb
            la mà. Clica un punt per obrir la fitxa de la cançó (lletra,
            metadades, enllaç a Viasona). Des d'allà, prem <strong>
            ≈ Cerca similars</strong> i s'afegeix un chip que filtra el
            mapa per cançons semblants a aquesta.
          </p>
          <Illustration label="Després de clicar un punt: la fitxa amb les accions a dalt.">
            <div className="mock-detail">
              <div className="mock-detail-head">
                <div className="mock-detail-title-block">
                  <div className="mock-detail-title">Boig per tu</div>
                  <div className="mock-detail-artist">Sau</div>
                </div>
                <div className="mock-detail-actions">
                  <span className="mock-pill mock-pill--brand">≈ Cerca similars</span>
                  <span className="mock-pill mock-pill--dark">Veure a Viasona ↗</span>
                </div>
              </div>
              <div className="mock-detail-meta">
                <span className="mock-tag" style={{ background: GENRE_COLORS['pop-rock'] }}>pop-rock</span>
                <span>Quina nit, la nit d'ahir</span>
                <span>1990</span>
              </div>
            </div>
          </Illustration>
        </FeatureCard>

        <FeatureCard
          number="04"
          title="Selecciona text de la lletra"
          subtitle="Converteix qualsevol fragment en un filtre nou"
        >
          <p>
            Dins la fitxa d'una cançó, <strong>selecciona</strong> un tros
            de la lletra, del títol o del nom de l'artista (o fes <strong>
            doble clic</strong> sobre una paraula per seleccionar-la
            sencera). Apareix una pastilla flotant just sota la selecció:
            clica-la i el fragment s'afegeix com a chip de cerca. Útil
            quan llegint la lletra ensopegues amb una imatge o un tema
            que vols explorar al mapa.
          </p>
          <Illustration label="La pastilla apareix sota el text seleccionat; tanca la fitxa i aplica el filtre.">
            <div className="mock-selection">
              <div className="mock-selection-lyrics">
                Si em dius adéu,<br />
                vull que el dia sigui{' '}
                <span className="mock-selection-highlight">net i clar</span>,<br />
                que cap ocell trenqui l'harmonia del seu cant.
              </div>
              <div className="mock-selection-action">
                <span aria-hidden="true">+</span>
                Afegir «net i clar» com a filtre
              </div>
            </div>
          </Illustration>
        </FeatureCard>

        <FeatureCard
          number="05"
          title="Desglossament de puntuació"
          subtitle="Quina cançó encaixa millor amb quin filtre?"
        >
          <p>
            Cada resultat mostra una bolla amb el <strong>percentatge de
            similitud</strong>. Clica-la per obrir un panell amb el
            percentatge de cada filtre per separat — així entens si una
            cançó passa perquè és perfecta a un dels filtres o perquè és
            correcta a tots. Funciona també amb un sol chip (és l'única
            manera de veure el detall sense fer la mitjana).
          </p>
          <Illustration label="La bolla és clicable sempre que hi hagi com a mínim un filtre.">
            <div className="mock-breakdown">
              <div className="mock-result-card">
                <div className="mock-result-body">
                  <div className="mock-result-title">Vaig com les aus</div>
                  <div className="mock-result-artist">Lluís Llach</div>
                </div>
                <div className="mock-ring" style={{ '--pct': 72 }}>
                  <span>72</span>
                </div>
              </div>
              <div className="mock-arrow" aria-hidden="true">→</div>
              <div className="mock-breakdown-panel">
                <div className="mock-breakdown-head">Per filtre</div>
                <ul>
                  <li><span>amor</span><span style={{ color: 'hsl(95, 70%, 36%)' }}>81%</span></li>
                  <li><span>tristesa</span><span style={{ color: 'hsl(60, 70%, 40%)' }}>63%</span></li>
                  <li className="mock-breakdown-total"><span>Mitjana</span><span>72%</span></li>
                </ul>
              </div>
            </div>
          </Illustration>
        </FeatureCard>

        <FeatureCard
          number="06"
          title="Exporta els top resultats"
          subtitle="Top 10, 50, 100 — o un número concret"
        >
          <p>
            A dalt de la llista esquerra, prem <strong>Exportar</strong>.
            Tries quants vols (preset o número personalitzat) i et baixa
            un CSV amb les columnes <code>rank, id, title, artist, album,
            year, genre, score</code> — llest per a Excel o per processar.
          </p>
          <Illustration label="El menú apareix amb un preset i camp lliure.">
            <div className="mock-export">
              <div className="mock-export-btn">↓ Exportar</div>
              <div className="mock-export-menu">
                <div className="mock-export-head">Quants resultats?</div>
                <div className="mock-export-presets">
                  <span className="mock-export-preset">Top 10</span>
                  <span className="mock-export-preset mock-export-preset--hot">Top 50</span>
                  <span className="mock-export-preset">Top 100</span>
                </div>
                <div className="mock-export-custom">
                  <span className="mock-export-input">27</span>
                  <span className="mock-export-submit">Exporta</span>
                </div>
              </div>
            </div>
          </Illustration>
        </FeatureCard>

        <FeatureCard
          number="07"
          title="Mou-te pel mapa"
          subtitle="Zoom amb la roda · arrossega per moure"
        >
          <p>
            Amb la roda del ratolí fas <strong>zoom</strong> centrat al
            cursor. Arrossega amb el ratolí per moure la vista. El clic
            dret està desactivat: només esquerra cliqua punts.
          </p>
          <Illustration label="Cap menú contextual; clic = obrir cançó.">
            <div className="mock-mapcontrols">
              <span className="mock-kbd-chip">🖱 roda → zoom</span>
              <span className="mock-kbd-chip">🖱 arrossega → mou</span>
              <span className="mock-kbd-chip">clic esquerre → obre cançó</span>
            </div>
          </Illustration>
        </FeatureCard>

        <FeatureCard
          number="08"
          title="Cercador instantani"
          subtitle="Una altra eina: per nom, no per significat"
        >
          <p>
            Si saps el grup, el títol o un tros de lletra exacte, ves al{' '}
            <strong>Cercador</strong> (botó de la capçalera). Té correcció
            ortogràfica i resultats en temps real per cada tecla:
            <em> grups, lletres i notícies</em> alhora.
          </p>
          <Illustration label="Tolerància a typos: 'sau' → 'Sau', 'bog per tu' → 'Boig per Tu'.">
            <div className="mock-cercador">
              <div className="mock-cercador-input">
                <span className="mock-cercador-icon">🔍</span>
                <span className="mock-cercador-text">bog per tu</span>
              </div>
              <div className="mock-cercador-correction">
                Volies dir <span className="mock-correction-pill">boig per tu</span>?
              </div>
            </div>
          </Illustration>
        </FeatureCard>

        <FeatureCard
          number="09"
          title="Petits detalls"
          subtitle="Coses que pots provar"
        >
          <ul className="help-tips">
            <li>El comptador <strong>"N / 5000 cançons"</strong> dalt a la dreta s'actualitza amb cada filtre.</li>
            <li>El botó <strong>Reinicia</strong> a la barra de cerca esborra tots els filtres d'un cop.</li>
            <li>Si poses un chip <strong>similars a "X"</strong>, X apareix al mapa com un <strong>diamant</strong>, no com un punt.</li>
            <li>La barra ressalta sempre l'<strong>últim filtre afegit</strong> al títol dels resultats.</li>
            <li>Tot funciona també en <strong>fosc</strong>: prem el commutador de la capçalera.</li>
          </ul>
        </FeatureCard>

        <footer className="help-footer">
          <button className="help-cta" onClick={onClose} type="button">
            Tornar al mapa
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 5l7 7-7 7" />
            </svg>
          </button>
        </footer>
      </main>
    </div>
  )
}

function FeatureCard({ number, title, subtitle, children }) {
  return (
    <section className="help-card">
      <div className="help-card-head">
        <span className="help-card-num">{number}</span>
        <div>
          <h2 className="help-card-title">{title}</h2>
          <p className="help-card-subtitle">{subtitle}</p>
        </div>
      </div>
      <div className="help-card-body">{children}</div>
    </section>
  )
}

function Illustration({ children, label }) {
  return (
    <div className="help-illustration">
      <div className="help-illustration-frame">{children}</div>
      {label && <div className="help-illustration-cap">{label}</div>}
    </div>
  )
}

function Kbd({ children }) {
  return <kbd className="help-kbd">{children}</kbd>
}

function Cross() {
  return <span className="mock-chip-x" aria-hidden="true">×</span>
}
