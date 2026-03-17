import { Recommendation, SearchResponse, SongDetail } from '@/lib/types';

const SONGS: SongDetail[] = [
  {
    id: 'llum-dins-la-pluja',
    title: 'Llum dins la pluja',
    artist: 'Els Miralls',
    album: 'Ciutat de paper',
    year: 2021,
    language: 'Catalan',
    duration: '3:42',
    mood_tags: ['nostalgic', 'hopeful', 'night-drive'],
    genres: ['indie pop', 'catalan pop'],
    snippet: 'A hopeful indie-pop track about finding direction after emotional chaos.',
    lyrics_preview: 'Quan la ciutat es trenca en llum / jo busco el teu nom sota la pluja...',
    narrative: 'Useful for lyric lookups, emotional discovery, and similarity recommendations.',
  },
  {
    id: 'foc-a-la-pell',
    title: 'Foc a la pell',
    artist: 'Clara Serra',
    album: 'Satèl·lits',
    year: 2019,
    language: 'Catalan',
    duration: '4:01',
    mood_tags: ['intense', 'romantic', 'anthemic'],
    genres: ['pop rock'],
    snippet: 'A dramatic pop-rock song about desire, momentum, and impossible restraint.',
    lyrics_preview: 'Portes foc a la pell / i un estiu sencer dins la mirada...',
    narrative: 'Strong candidate for typo-tolerant classic search and energetic mood-based discovery.',
  },
  {
    id: 'cartes-que-no-envio',
    title: 'Cartes que no envio',
    artist: 'Nora Vallès',
    album: 'Habitacions obertes',
    year: 2020,
    language: 'Catalan',
    duration: '3:18',
    mood_tags: ['melancholic', 'intimate', 'acoustic'],
    genres: ['folk', 'singer-songwriter'],
    snippet: 'An intimate acoustic ballad built around unsent letters and unresolved emotions.',
    lyrics_preview: "T'escric paraules petites / que mai no s'atreveixen a sortir del calaix...",
    narrative: 'Good fit for natural-language prompts about heartbreak, distance, and quiet reflection.',
  },
  {
    id: 'dies-de-vidre',
    title: 'Dies de vidre',
    artist: 'Pol Nord',
    album: 'Vertical',
    year: 2022,
    language: 'Catalan',
    duration: '3:55',
    mood_tags: ['reflective', 'urban', 'atmospheric'],
    genres: ['alternative', 'electronic pop'],
    snippet: 'Atmospheric alternative pop with urban imagery and a fragile emotional tone.',
    lyrics_preview: 'Dies de vidre, carrers oberts / els semàfors parlen més que nosaltres...',
    narrative: 'Suitable for semantic retrieval when users describe a feeling instead of exact lyrics.',
  },
  {
    id: 'mar-endins',
    title: 'Mar endins',
    artist: 'Brisa Roja',
    album: 'Sal oberta',
    year: 2018,
    language: 'Catalan',
    duration: '4:12',
    mood_tags: ['freedom', 'summer', 'uplifting'],
    genres: ['folk pop'],
    snippet: 'A bright, coastal folk-pop song about movement, release, and open horizons.',
    lyrics_preview: 'Mar endins, sense mapa / deixo enrere el soroll i els dubtes...',
    narrative: 'Useful for recommendation panels and discovery journeys around freedom and travel.',
  },
  {
    id: 'ombra-i-or',
    title: 'Ombra i or',
    artist: 'Vera Soler',
    album: 'Línies invisibles',
    year: 2023,
    language: 'Catalan',
    duration: '3:28',
    mood_tags: ['cinematic', 'mysterious', 'elegant'],
    genres: ['dream pop'],
    snippet: 'Dream-pop textures and cinematic lyricism centered on contrast and transformation.',
    lyrics_preview: "Entre l'ombra i l'or / hi ha un silenci que encara em coneix...",
    narrative: 'Ideal for demoing semantic search around imagery, elegance, or mood-rich prompts.',
  },
];

function tokenize(text: string): string[] {
  return text.toLowerCase().replace(/-/g, ' ').split(/\s+/).filter(Boolean);
}

function songText(song: SongDetail): string {
  return [song.title, song.artist, song.album, song.snippet, song.lyrics_preview, song.narrative, ...song.mood_tags, ...song.genres]
    .join(' ')
    .toLowerCase();
}

function scoreSong(song: SongDetail, query: string, mode: 'classic' | 'smart'): number {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return mode === 'classic' ? 0.52 : 0.72;
  }

  const haystack = songText(song);
  const tokens = tokenize(normalized);
  const overlap = tokens.filter((token) => haystack.includes(token)).length;
  const containsBonus = haystack.includes(normalized) ? 0.28 : 0;
  const modeBias = mode === 'smart' ? 0.08 : 0;
  return Math.min(0.99, Number((0.34 + overlap * 0.12 + containsBonus + modeBias).toFixed(2)));
}

export function buildMockSearchResponse(query: string, mode: 'classic' | 'smart'): SearchResponse {
  const results = SONGS.map((song) => ({
    id: song.id,
    title: song.title,
    artist: song.artist,
    album: song.album,
    year: song.year,
    language: song.language,
    mood_tags: song.mood_tags,
    snippet: song.snippet,
    match_reason:
      mode === 'classic'
        ? `Matched title, lyric fragment, or metadata for "${query}".`
        : `Matched the intent behind "${query}" through mood, narrative, and semantic similarity.`,
    similarity_score: scoreSong(song, query, mode),
  })).sort((left, right) => right.similarity_score - left.similarity_score);

  return {
    mode,
    query,
    total_results: results.length,
    took_ms: mode === 'classic' ? 86 : 132,
    suggestions: ['amor impossible', 'cançons per conduir de nit', 'balades tristes en català'],
    results,
  };
}

export function getMockSongDetail(songId: string): SongDetail | undefined {
  return SONGS.find((song) => song.id === songId);
}

export function getMockRecommendations(songId: string): Recommendation[] {
  const current = SONGS.find((song) => song.id === songId);
  if (!current) {
    return [];
  }

  const currentTags = new Set(current.mood_tags);
  return SONGS.filter((song) => song.id !== songId)
    .map((song) => {
      const sharedTags = song.mood_tags.filter((tag) => currentTags.has(tag));
      return {
        id: song.id,
        title: song.title,
        artist: song.artist,
        reason: sharedTags.length > 0
          ? `Shares mood tags: ${sharedTags.join(', ')}.`
          : 'Close lyrical tone and complementary discovery profile.',
        similarity_score: Math.min(0.97, Number((0.58 + sharedTags.length * 0.12).toFixed(2))),
      };
    })
    .sort((left, right) => right.similarity_score - left.similarity_score)
    .slice(0, 3);
}
