import { ResultCard } from '@/components/result-card';
import { SearchForm } from '@/components/search-form';
import { getClassicResults, getSmartResults } from '@/lib/api';

interface SearchPageProps {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}

function getSearchParam(value: string | string[] | undefined, fallback: string): string {
  if (Array.isArray(value)) {
    return value[0] ?? fallback;
  }
  return value ?? fallback;
}

export default async function SearchPage({ searchParams }: SearchPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const query = getSearchParam(resolvedSearchParams.q, 'amor impossible');
  const requestedMode = getSearchParam(resolvedSearchParams.mode, 'hybrid');

  const [classicResults, smartResults] = await Promise.all([
    getClassicResults(query),
    getSmartResults(query),
  ]);

  return (
    <div className="page-stack">
      <section className="page-heading card glass-card">
        <span className="pill">Search showcase</span>
        <h1>Hybrid search comparison</h1>
        <p>
          Compare the fast, structured search path with the semantic interpretation path using the same query.
        </p>
        <div className="metric-row">
          <div>
            <span className="metric-label">Current query</span>
            <strong>{query}</strong>
          </div>
          <div>
            <span className="metric-label">Demo focus</span>
            <strong>{requestedMode}</strong>
          </div>
        </div>
      </section>

      <section className="section-grid two-columns">
        <SearchForm
          defaultValue={query}
          mode="classic"
          label="Classic lookup"
          placeholder="Try a title, lyric fragment, or misspelled phrase"
        />
        <SearchForm
          defaultValue={query}
          mode="smart"
          label="Smart prompt"
          placeholder="Describe a mood, scene, or listening intent"
        />
      </section>

      <section className="section-grid results-section">
        <div className="results-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Traditional engine</span>
              <h2>Classic results</h2>
            </div>
            <span className="score-badge">{classicResults.took_ms} ms</span>
          </div>
          <div className="results-grid">
            {classicResults.results.slice(0, 4).map((result) => (
              <ResultCard key={`classic-${result.id}`} result={result} mode="classic" />
            ))}
          </div>
        </div>

        <div className="results-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Semantic engine</span>
              <h2>Smart results</h2>
            </div>
            <span className="score-badge">{smartResults.took_ms} ms</span>
          </div>
          <div className="results-grid">
            {smartResults.results.slice(0, 4).map((result) => (
              <ResultCard key={`smart-${result.id}`} result={result} mode="smart" />
            ))}
          </div>
        </div>
      </section>

      <section className="card suggestions-card">
        <span className="eyebrow">Prompt suggestions</span>
        <div className="tag-row">
          {smartResults.suggestions.map((suggestion) => (
            <a
              key={suggestion}
              className="tag-chip tag-chip--interactive"
              href={`/search?q=${encodeURIComponent(suggestion)}&mode=smart`}
            >
              {suggestion}
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}
