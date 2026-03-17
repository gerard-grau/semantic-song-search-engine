import Link from 'next/link';

import { SearchResult } from '@/lib/types';

interface ResultCardProps {
  result: SearchResult;
  mode: 'classic' | 'smart';
}

export function ResultCard({ result, mode }: ResultCardProps) {
  return (
    <article className="result-card card">
      <div className="result-card__top">
        <span className={`mode-badge ${mode === 'classic' ? 'mode-badge--classic' : 'mode-badge--smart'}`}>
          {mode === 'classic' ? 'Classic' : 'Smart'}
        </span>
        <span className="score-badge">{Math.round(result.similarity_score * 100)}%</span>
      </div>

      <div className="result-card__body">
        <h3>{result.title}</h3>
        <p className="result-meta">
          {result.artist} · {result.album} · {result.year}
        </p>
        <p className="result-snippet">{result.snippet}</p>
        <p className="result-reason">{result.match_reason}</p>
      </div>

      <div className="tag-row">
        {result.mood_tags.map((tag) => (
          <span key={`${result.id}-${tag}`} className="tag-chip">
            {tag}
          </span>
        ))}
      </div>

      <div className="result-card__footer">
        <span className="caption">Language: {result.language}</span>
        <Link href={`/song/${result.id}`} className="inline-link">
          Open detail →
        </Link>
      </div>
    </article>
  );
}
