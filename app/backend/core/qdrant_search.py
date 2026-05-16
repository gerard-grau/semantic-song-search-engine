"""
Qdrant-based semantic search for the Cercador intelligent.

Connects to a Docker Qdrant instance at localhost:6333. Gracefully degrades
to returning None on any connection or query failure so the caller can fall
back to the existing matrix-based approach.

Collections (populated by ml/embeddings/index_qdrant_docker.py):

  songs_qualitative   — one point per song, qualitative_description vector.
                        Good for mood / theme / topic queries.
  songs_lyrics_chunks — one point per ~100-word lyrics chunk.
                        Good for lyric-content queries; results are
                        deduplicated to the best chunk per song before returning.

Public API
----------
  is_available()          → bool
  search_qualitative(...) → list[dict] | None
  search_lyrics_chunks(...)→ list[dict] | None

A None return always means "Qdrant unavailable — use fallback". An empty list
means "Qdrant answered but found nothing above the threshold".
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
_TIMEOUT    = 2.0   # seconds for each Qdrant request

QUALITATIVE_COLLECTION = "songs_qualitative"
LYRICS_COLLECTION      = "songs_lyrics_chunks"

# Score threshold applied before Python-side deduplication. Keeps results
# that are at least weakly relevant so the floor isn't too aggressive.
_SCORE_THRESHOLD = 0.30

# Retry: only attempt reconnection every N seconds after a failure so we
# don't hammer localhost on every keystroke when Docker is not running.
_RETRY_INTERVAL: float = 30.0

_client = None
_last_attempt: float = 0.0


def _get_client():
    """Return a cached QdrantClient or None if unavailable."""
    global _client, _last_attempt

    if _client is not None:
        return _client

    now = time.monotonic()
    if now - _last_attempt < _RETRY_INTERVAL:
        return None
    _last_attempt = now

    try:
        from qdrant_client import QdrantClient
        c = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=_TIMEOUT)
        c.get_collections()          # lightweight health-check
        _client = c
        logger.info("Connected to Qdrant at %s:%s", QDRANT_HOST, QDRANT_PORT)
        return _client
    except Exception as exc:
        logger.debug("Qdrant unavailable: %s", exc)
        return None


def _drop_client() -> None:
    """Force reconnect on next call (e.g., after a search error)."""
    global _client
    _client = None


def _payload_filter(artist: str | None):
    """Build a Qdrant payload filter restricted to a specific artist name."""
    if not artist:
        return None
    from qdrant_client.models import FieldCondition, Filter, MatchValue
    return Filter(must=[FieldCondition(key="artist", match=MatchValue(value=artist))])


def is_available() -> bool:
    """True if a Qdrant Docker instance is reachable and collections exist."""
    client = _get_client()
    if client is None:
        return False
    try:
        names = {c.name for c in client.get_collections().collections}
        return QUALITATIVE_COLLECTION in names and LYRICS_COLLECTION in names
    except Exception:
        _drop_client()
        return False


def search_qualitative(
    query_vec: list[float],
    limit: int = 5,
    artist_filter: str | None = None,
    exclude_ids: set[int] | None = None,
) -> list[dict] | None:
    """Search the qualitative_description collection.

    Returns a list of result dicts (may be empty), or None if Qdrant is
    unavailable. Each dict has keys: id, title, artist, album, score,
    lyrics_snippet (empty — caller enriches from visible index).
    """
    client = _get_client()
    if client is None:
        return None

    # Fetch extra to survive exclude_ids filtering
    fetch = limit + (len(exclude_ids) if exclude_ids else 0) + 5
    try:
        hits = client.search(
            collection_name=QUALITATIVE_COLLECTION,
            query_vector=query_vec,
            limit=fetch,
            query_filter=_payload_filter(artist_filter),
            with_payload=True,
            score_threshold=_SCORE_THRESHOLD,
        )
    except Exception as exc:
        logger.warning("Qdrant qualitative search error: %s", exc)
        _drop_client()
        return None

    out: list[dict] = []
    for h in hits:
        sid = int(h.payload.get("id_lyrics", 0))
        if exclude_ids and sid in exclude_ids:
            continue
        out.append({
            "id":             sid,
            "title":          str(h.payload.get("title",  "")),
            "artist":         str(h.payload.get("artist", "")),
            "album":          str(h.payload.get("album",  "")),
            "lyrics_snippet": "",
            "score":          round(max(0.0, min(1.0, float(h.score))), 4),
        })
        if len(out) >= limit:
            break
    return out


def search_lyrics_chunks(
    query_vec: list[float],
    limit: int = 3,
    artist_filter: str | None = None,
    exclude_ids: set[int] | None = None,
) -> list[dict] | None:
    """Search the lyrics-chunks collection, returning best chunk per song.

    Fetches limit×8 raw chunk hits then deduplicates to the highest-scoring
    chunk per song. Returns None if Qdrant is unavailable.

    Each result dict has: id, title, artist, album, lyrics_snippet (the
    matching chunk text, up to 250 chars), score.
    """
    client = _get_client()
    if client is None:
        return None

    raw_limit = limit * 8
    try:
        hits = client.search(
            collection_name=LYRICS_COLLECTION,
            query_vector=query_vec,
            limit=raw_limit,
            query_filter=_payload_filter(artist_filter),
            with_payload=True,
            score_threshold=_SCORE_THRESHOLD,
        )
    except Exception as exc:
        logger.warning("Qdrant lyrics search error: %s", exc)
        _drop_client()
        return None

    # Deduplicate: keep the best-scoring chunk per song id
    best: dict[int, dict] = {}
    for h in hits:
        sid   = int(h.payload.get("id_lyrics", 0))
        score = float(h.score)
        if exclude_ids and sid in exclude_ids:
            continue
        if sid not in best or score > best[sid]["score"]:
            best[sid] = {
                "id":             sid,
                "title":          str(h.payload.get("title",              "")),
                "artist":         str(h.payload.get("artist",             "")),
                "album":          str(h.payload.get("album",              "")),
                "lyrics_snippet": str(h.payload.get("chunk_text_snippet", ""))[:250],
                "score":          round(max(0.0, min(1.0, score)), 4),
            }

    return sorted(best.values(), key=lambda x: x["score"], reverse=True)[:limit]
