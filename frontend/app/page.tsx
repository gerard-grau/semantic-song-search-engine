import Link from 'next/link';

import { HeroSearch } from '@/components/hero-search';

const featureCards = [
  {
    title: 'Fast classic retrieval',
    description: 'Search by title, lyric fragment, or metadata with a latency-focused interface.',
  },
  {
    title: 'Natural-language discovery',
    description: 'Use descriptive prompts to surface songs by feeling, theme, or similarity.',
  },
  {
    title: 'Demo-ready storytelling',
    description: 'A polished interface to show the search vision before the production engines are connected.',
  },
];

const stakeholderHighlights = [
  'Convincing visual demo without requiring production retrieval yet.',
  'Mock API contracts ready to be replaced with real classic and smart search services.',
  'Screens designed for usability tests and stakeholder walkthroughs.',
];

export default function HomePage() {
  return (
    <>
      <HeroSearch
        title="A modern hybrid search experience for music discovery"
        subtitle="This MVP showcases how Viasona can evolve from a slow exact-match search into a responsive, semantic, and visually polished discovery platform."
      />

      <section className="section-grid two-columns">
        {featureCards.map((card) => (
          <article key={card.title} className="card feature-card">
            <span className="eyebrow">Capability</span>
            <h2>{card.title}</h2>
            <p>{card.description}</p>
          </article>
        ))}
      </section>

      <section className="section-grid spotlight-layout">
        <article className="card spotlight-card">
          <span className="eyebrow">Stakeholder demo flow</span>
          <h2>Walk through the three core screens</h2>
          <ol className="check-list">
            <li>Start from the landing page and show both classic and smart search entry points.</li>
            <li>Open the search page to compare ranked results from both engines.</li>
            <li>Open a song page to present metadata, lyrical context, and recommendations.</li>
          </ol>
          <Link href="/search" className="button button-primary">
            Open demo search
          </Link>
        </article>

        <article className="card dark-card">
          <span className="eyebrow">Why this MVP matters</span>
          <ul className="bullet-stack">
            {stakeholderHighlights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </section>
    </>
  );
}
