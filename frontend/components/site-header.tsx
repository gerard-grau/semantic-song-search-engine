import Link from 'next/link';

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="container nav-shell">
        <Link href="/" className="brand-mark">
          <span className="brand-badge">VS</span>
          <div>
            <p className="eyebrow">Semantic Song Search</p>
            <p className="brand-subtitle">Stakeholder MVP</p>
          </div>
        </Link>

        <nav className="nav-links" aria-label="Primary navigation">
          <Link href="/">Overview</Link>
          <Link href="/search">Search demo</Link>
          <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
            API docs
          </a>
        </nav>
      </div>
    </header>
  );
}
