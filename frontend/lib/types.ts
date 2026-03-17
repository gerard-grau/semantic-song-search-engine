export type SearchMode = 'classic' | 'smart';

export interface SearchResult {
  id: string;
  title: string;
  artist: string;
  album: string;
  year: number;
  language: string;
  mood_tags: string[];
  snippet: string;
  match_reason: string;
  similarity_score: number;
}

export interface SearchResponse {
  mode: SearchMode;
  query: string;
  total_results: number;
  took_ms: number;
  suggestions: string[];
  results: SearchResult[];
}

export interface SongDetail {
  id: string;
  title: string;
  artist: string;
  album: string;
  year: number;
  language: string;
  duration: string;
  mood_tags: string[];
  genres: string[];
  snippet: string;
  lyrics_preview: string;
  narrative: string;
}

export interface Recommendation {
  id: string;
  title: string;
  artist: string;
  reason: string;
  similarity_score: number;
}
