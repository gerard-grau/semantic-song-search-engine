from __future__ import annotations

from typing import Iterable

from .schemas import Recommendation, SearchResponse, SearchResult, SongDetail


SONGS: list[SongDetail] = [
    SongDetail(
        id="llum-dins-la-pluja",
        title="Llum dins la pluja",
        artist="Els Miralls",
        album="Ciutat de paper",
        year=2021,
        language="Catalan",
        duration="3:42",
        mood_tags=["nostalgic", "hopeful", "night-drive"],
        genres=["indie pop", "catalan pop"],
        snippet="A hopeful indie-pop track about finding direction after emotional chaos.",
        lyrics_preview="Quan la ciutat es trenca en llum / jo busco el teu nom sota la pluja...",
        narrative="Useful for lyric lookups, emotional discovery, and similarity recommendations.",
    ),
    SongDetail(
        id="foc-a-la-pell",
        title="Foc a la pell",
        artist="Clara Serra",
        album="Satèl·lits",
        year=2019,
        language="Catalan",
        duration="4:01",
        mood_tags=["intense", "romantic", "anthemic"],
        genres=["pop rock"],
        snippet="A dramatic pop-rock song about desire, momentum, and impossible restraint.",
        lyrics_preview="Portes foc a la pell / i un estiu sencer dins la mirada...",
        narrative="Strong candidate for typo-tolerant classic search and energetic mood-based discovery.",
    ),
    SongDetail(
        id="cartes-que-no-envio",
        title="Cartes que no envio",
        artist="Nora Vallès",
        album="Habitacions obertes",
        year=2020,
        language="Catalan",
        duration="3:18",
        mood_tags=["melancholic", "intimate", "acoustic"],
        genres=["folk", "singer-songwriter"],
        snippet="An intimate acoustic ballad built around unsent letters and unresolved emotions.",
        lyrics_preview="T'escric paraules petites / que mai no s'atreveixen a sortir del calaix...",
        narrative="Good fit for natural-language prompts about heartbreak, distance, and quiet reflection.",
    ),
    SongDetail(
        id="dies-de-vidre",
        title="Dies de vidre",
        artist="Pol Nord",
        album="Vertical",
        year=2022,
        language="Catalan",
        duration="3:55",
        mood_tags=["reflective", "urban", "atmospheric"],
        genres=["alternative", "electronic pop"],
        snippet="Atmospheric alternative pop with urban imagery and a fragile emotional tone.",
        lyrics_preview="Dies de vidre, carrers oberts / els semàfors parlen més que nosaltres...",
        narrative="Suitable for semantic retrieval when users describe a feeling instead of exact lyrics.",
    ),
    SongDetail(
        id="mar-endins",
        title="Mar endins",
        artist="Brisa Roja",
        album="Sal oberta",
        year=2018,
        language="Catalan",
        duration="4:12",
        mood_tags=["freedom", "summer", "uplifting"],
        genres=["folk pop"],
        snippet="A bright, coastal folk-pop song about movement, release, and open horizons.",
        lyrics_preview="Mar endins, sense mapa / deixo enrere el soroll i els dubtes...",
        narrative="Useful for recommendation panels and discovery journeys around freedom and travel.",
    ),
    SongDetail(
        id="ombra-i-or",
        title="Ombra i or",
        artist="Vera Soler",
        album="Línies invisibles",
        year=2023,
        language="Catalan",
        duration="3:28",
        mood_tags=["cinematic", "mysterious", "elegant"],
        genres=["dream pop"],
        snippet="Dream-pop textures and cinematic lyricism centered on contrast and transformation.",
        lyrics_preview="Entre l'ombra i l'or / hi ha un silenci que encara em coneix...",
        narrative="Ideal for demoing semantic search around imagery, elegance, or mood-rich prompts.",
    ),
]


def _tokenize(text: str) -> set[str]:
    return {token for token in text.lower().replace("-", " ").split() if token}


def _catalog_text(song: SongDetail) -> str:
    fields = [
        song.title,
        song.artist,
        song.album,
        song.snippet,
        song.lyrics_preview,
        song.narrative,
        " ".join(song.mood_tags),
        " ".join(song.genres),
    ]
    return " ".join(fields).lower()


def _score_song(song: SongDetail, query: str, mode: str) -> float:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return 0.5 if mode == "classic" else 0.7

    haystack = _catalog_text(song)
    query_tokens = _tokenize(normalized_query)
    overlap = len(query_tokens & _tokenize(haystack))
    contains_bonus = 0.3 if normalized_query in haystack else 0.0
    mode_bias = 0.08 if mode == "smart" and any(tag in haystack for tag in ["mood", "emotion", "heartbreak"]) else 0.0
    score = min(0.99, 0.32 + overlap * 0.14 + contains_bonus + mode_bias)
    return round(score, 2)


def _build_reason(song: SongDetail, query: str, mode: str) -> str:
    if mode == "classic":
        return f"Matched title, lyric fragment, or metadata for '{query}'."
    return f"Matched the intent behind '{query}' through mood, narrative, and semantic similarity."


def _build_result(song: SongDetail, query: str, mode: str) -> SearchResult:
    return SearchResult(
        id=song.id,
        title=song.title,
        artist=song.artist,
        album=song.album,
        year=song.year,
        language=song.language,
        mood_tags=song.mood_tags,
        snippet=song.snippet,
        match_reason=_build_reason(song, query, mode),
        similarity_score=_score_song(song, query, mode),
    )


def _sort_results(results: Iterable[SearchResult]) -> list[SearchResult]:
    return sorted(results, key=lambda item: item.similarity_score, reverse=True)


def search_catalog(query: str, mode: str) -> SearchResponse:
    results = _sort_results(_build_result(song, query, mode) for song in SONGS)
    filtered_results = [result for result in results if result.similarity_score >= (0.4 if mode == "classic" else 0.45)]
    if not filtered_results:
        filtered_results = results[:3]

    suggestions = [
        "amor impossible",
        "cançons per conduir de nit",
        "balades tristes en català",
    ]

    return SearchResponse(
        mode=mode,
        query=query,
        total_results=len(filtered_results),
        took_ms=86 if mode == "classic" else 132,
        suggestions=suggestions,
        results=filtered_results,
    )


def get_song(song_id: str) -> SongDetail | None:
    for song in SONGS:
        if song.id == song_id:
            return song
    return None


def get_recommendations(song_id: str) -> list[Recommendation]:
    current_song = get_song(song_id)
    if current_song is None:
        return []

    recommendations: list[Recommendation] = []
    current_tags = set(current_song.mood_tags)
    for candidate in SONGS:
        if candidate.id == song_id:
            continue
        shared_tags = current_tags & set(candidate.mood_tags)
        score = 0.58 + len(shared_tags) * 0.12
        reason = (
            f"Shares mood tags: {', '.join(sorted(shared_tags))}."
            if shared_tags
            else "Close lyrical tone and complementary discovery profile."
        )
        recommendations.append(
            Recommendation(
                id=candidate.id,
                title=candidate.title,
                artist=candidate.artist,
                reason=reason,
                similarity_score=min(round(score, 2), 0.97),
            )
        )

    return sorted(recommendations, key=lambda item: item.similarity_score, reverse=True)[:3]
