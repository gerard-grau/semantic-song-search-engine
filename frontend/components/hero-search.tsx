import Link from 'next/link';

interface HeroSearchProps {
  title: string;
  subtitle: string;
  defaultClassicQuery?: string;
  defaultSmartQuery?: string;
}

export function HeroSearch({
  title,
  subtitle,
  defaultClassicQuery = 'amor impossible',
  defaultSmartQuery = 'songs for a nostalgic night drive',
}: HeroSearchProps) {
  return (
    <section className="hero-panel">
      <div className="hero-copy">
        <span className="pill">Hybrid search MVP</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>

        <div className="hero-actions">
          <Link href={`/search?q=${encodeURIComponent(defaultClassicQuery)}&mode=classic`} className="button button-primary">
            Try classic search
          </Link>
          <Link href={`/search?q=${encodeURIComponent(defaultSmartQuery)}&mode=smart`} className="button button-secondary">
            Try smart search
          </Link>
        </div>
      </div>

      <div className="hero-showcase card glass-card">
        <div className="showcase-header">
          <span className="eyebrow">Demo experience</span>
          <span className="metric-chip">Latency target &lt; 1s</span>
        </div>

        <div className="showcase-grid">
          <div className="mini-panel">
            <h3>Classic engine</h3>
            <p>Typo-tolerant, fast, and designed around lyrics plus metadata lookup.</p>
          </div>
          <div className="mini-panel accent-panel">
            <h3>Smart engine</h3>
            <p>Natural-language discovery for themes, moods, and related songs.</p>
          </div>
        </div>

        <div className="query-stack">
          <div className="query-card">
            <span className="query-label">Classic query</span>
            <p>{defaultClassicQuery}</p>
          </div>
          <div className="query-card">
            <span className="query-label">Smart query</span>
            <p>{defaultSmartQuery}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
