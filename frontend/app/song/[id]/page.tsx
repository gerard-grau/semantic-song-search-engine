import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ResultCard } from '@/components/result-card';
import { getClassicResults, getRecommendations, getSongDetail } from '@/lib/api';

interface SongPageProps {
  params: Promise<{ id: string }>;
}

export default async function SongPage({ params }: SongPageProps) {
  const { id } = await params;
  const song = await getSongDetail(id);

  if (!song) {
    notFound();
  }

  const [recommendations, relatedClassic] = await Promise.all([
    getRecommendations(id),
    getClassicResults(song.title),
  ]);

  return (
    <div className="page-stack">
      <section className="page-heading card glass-card">
        <span className="pill">Song detail demo</span>
        <h1>{song.title}</h1>
        <p>
          {song.artist} · {song.album} · {song.year} · {song.duration}
        </p>
        <div className="tag-row">
          {song.mood_tags.map((tag) => (
            <span key={tag} className="tag-chip">
              {tag}
            </span>
          ))}
        </div>
      </section>

      <section className="section-grid detail-layout">
        <article className="card detail-card">
          <span className="eyebrow">Narrative context</span>
          <p className="lead">{song.snippet}</p>
          <div className="content-block">
            <h2>Lyrics preview</h2>
            <p>{song.lyrics_preview}</p>
          </div>
          <div className="content-block">
            <h2>Why this page exists in the MVP</h2>
            <p>{song.narrative}</p>
          </div>
        </article>

        <article className="card detail-card detail-card--dark">
          <span className="eyebrow">Metadata</span>
          <dl className="metadata-grid">
            <div>
              <dt>Language</dt>
              <dd>{song.language}</dd>
            </div>
            <div>
              <dt>Genres</dt>
              <dd>{song.genres.join(', ')}</dd>
            </div>
            <div>
              <dt>Primary use case</dt>
              <dd>Lyrics lookup + discovery</dd>
            </div>
            <div>
              <dt>Prototype state</dt>
              <dd>Mock content, real UI contract</dd>
            </div>
          </dl>
          <Link href={`/search?q=${encodeURIComponent(song.title)}&mode=classic`} className="button button-secondary">
            Search similar entries
          </Link>
        </article>
      </section>

      <section className="section-grid results-section">
        <div className="results-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Recommendations</span>
              <h2>Related songs</h2>
            </div>
          </div>
          <div className="results-grid">
            {recommendations.map((item) => (
              <article key={item.id} className="card result-card">
                <div className="result-card__top">
                  <span className="mode-badge mode-badge--smart">Recommended</span>
                  <span className="score-badge">{Math.round(item.similarity_score * 100)}%</span>
                </div>
                <h3>{item.title}</h3>
                <p className="result-meta">{item.artist}</p>
                <p className="result-reason">{item.reason}</p>
                <div className="result-card__footer">
                  <span className="caption">Mock recommendation</span>
                  <Link href={`/song/${item.id}`} className="inline-link">
                    View song →
                  </Link>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="results-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Classic engine preview</span>
              <h2>Related lookup results</h2>
            </div>
          </div>
          <div className="results-grid">
            {relatedClassic.results.slice(0, 3).map((result) => (
              <ResultCard key={result.id} result={result} mode="classic" />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
