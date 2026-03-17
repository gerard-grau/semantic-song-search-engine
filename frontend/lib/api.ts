import { buildMockSearchResponse, getMockRecommendations, getMockSongDetail } from '@/lib/mock-data';
import { Recommendation, SearchResponse, SongDetail } from '@/lib/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function safeFetch<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      cache: 'no-store',
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function getClassicResults(query: string): Promise<SearchResponse> {
  const result = await safeFetch<SearchResponse>(`/search/classic?q=${encodeURIComponent(query)}`);
  return result ?? buildMockSearchResponse(query, 'classic');
}

export async function getSmartResults(query: string): Promise<SearchResponse> {
  const result = await safeFetch<SearchResponse>(`/search/smart?q=${encodeURIComponent(query)}`);
  return result ?? buildMockSearchResponse(query, 'smart');
}

export async function getSongDetail(songId: string): Promise<SongDetail | null> {
  const result = await safeFetch<SongDetail>(`/songs/${encodeURIComponent(songId)}`);
  return result ?? getMockSongDetail(songId) ?? null;
}

export async function getRecommendations(songId: string): Promise<Recommendation[]> {
  const result = await safeFetch<Recommendation[]>(`/songs/${encodeURIComponent(songId)}/recommendations`);
  return result ?? getMockRecommendations(songId);
}
