"""
Qdrant-based semantic search for the Cercador intelligent.

Connects to a Qdrant instance at localhost:6333. Gracefully degrades
to returning None on any connection or query failure so the caller can fall
back to the existing matrix-based approach.

Collections (populated by ml/embeddings/index_qdrant_docker.py):

  songs_qualitative   — one point per song, qualitative_description vector.
                        Good for mood / theme / topic queries.
  songs_lyrics_chunks — one point per ~100-word lyrics chunk.
                        Good for lyric-content queries; results are
                        deduplicated to the best chunk per song before returning.

Lyrics search is *hybrid*: dense BGE-M3 semantic search + keyword full-text
search on chunk_text_snippet, merged with Reciprocal Rank Fusion (RRF).
The keyword component catches exact phrase recall ("tinc dos cors") that
dense embeddings miss when the query is a short verbatim quote.

Public API
----------
  is_available()          → bool
  search_qualitative(...) → list[dict] | None
  search_lyrics_chunks(...)→ list[dict] | None   (hybrid: dense + keyword)

A None return always means "Qdrant unavailable — use fallback". An empty list
means "Qdrant answered but found nothing above the threshold".
"""

from __future__ import annotations

import logging
import math
import time

logger = logging.getLogger(__name__)

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
_TIMEOUT    = 5.0   # seconds per Qdrant request

QUALITATIVE_COLLECTION = "songs_qualitative"
LYRICS_COLLECTION      = "songs_lyrics_chunks"

_SCORE_THRESHOLD = 0.28   # minimum cosine for dense results (slightly relaxed)
_RRF_K           = 60     # standard RRF constant

_RETRY_INTERVAL: float = 30.0

_client = None
_last_attempt: float = 0.0
_text_index_ensured: bool = False

_CE_MODEL_NAME = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
_cross_encoder = None


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
        c.get_collections()
        _client = c
        logger.info("Connected to Qdrant at %s:%s", QDRANT_HOST, QDRANT_PORT)
        _ensure_text_index(c)
        return _client
    except Exception as exc:
        logger.debug("Qdrant unavailable: %s", exc)
        return None


def _drop_client() -> None:
    global _client
    _client = None


def _get_cross_encoder():
    """Lazy-load the multilingual cross-encoder (downloaded on first call)."""
    global _cross_encoder
    if _cross_encoder is not None:
        return _cross_encoder
    try:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder(_CE_MODEL_NAME)
        logger.info("Cross-encoder loaded: %s", _CE_MODEL_NAME)
        return _cross_encoder
    except Exception as exc:
        logger.warning("Cross-encoder unavailable: %s", exc)
        return None


def _ce_rerank(query_text: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Re-score candidates with the cross-encoder and return top_k.

    Scores are raw cross-encoder logits passed through sigmoid so the
    frontend can still render them as a [0, 1] match percentage.
    Falls back to the original ordering on any error.
    """
    if not candidates or not query_text:
        return candidates[:top_k]
    ce = _get_cross_encoder()
    if ce is None:
        return candidates[:top_k]
    try:
        pairs = [(query_text, c["lyrics_snippet"]) for c in candidates]
        raw_scores = ce.predict(pairs)
        reranked = sorted(
            zip(raw_scores, candidates),
            key=lambda x: x[0],
            reverse=True,
        )
        out = []
        for raw, c in reranked[:top_k]:
            c = dict(c)
            c["score"] = round(1.0 / (1.0 + math.exp(-float(raw))), 4)
            out.append(c)
        return out
    except Exception as exc:
        logger.warning("Cross-encoder reranking error: %s", exc)
        return candidates[:top_k]


def _ensure_text_index(client) -> None:
    """Create full-text index on chunk_text_snippet (idempotent)."""
    global _text_index_ensured
    if _text_index_ensured:
        return
    try:
        from qdrant_client.models import TextIndexParams, TokenizerType
        client.create_payload_index(
            collection_name=LYRICS_COLLECTION,
            field_name="chunk_text_snippet",
            field_schema=TextIndexParams(
                type="text",
                tokenizer=TokenizerType.WHITESPACE,
                lowercase=True,
            ),
        )
        _text_index_ensured = True
        logger.info("Full-text index on chunk_text_snippet ensured")
    except Exception as exc:
        # Index likely already exists — not an error.
        _text_index_ensured = True
        logger.debug("Text index setup: %s", exc)


def _payload_filter(artist: str | None):
    """Qdrant filter restricted to one artist (MatchAny over name variants)."""
    if not artist:
        return None
    from qdrant_client.models import FieldCondition, Filter, MatchAny
    variants = list({
        artist,
        artist.strip(),
        artist.lower(),
        artist.lower().strip(),
    })
    return Filter(must=[FieldCondition(key="artist", match=MatchAny(any=variants))])


# Common short Catalan/Spanish function words to skip even when ≥3 chars
_STOP_WORDS = frozenset({
    "que", "els", "les", "del", "una", "uns", "ens", "com", "per",
    "amb", "tot", "mes", "mai", "ara", "molt", "però", "dels", "les",
    "uns", "han", "hem", "van", "son", "era", "ben", "cap", "poc",
    "tan", "cal", "fer", "ser", "más", "que", "los", "las", "del",
    "con", "por", "sin", "hay", "era", "fue",
})


def _extract_keywords(text: str) -> list[str]:
    """Pull meaningful tokens (≥3 chars, excluding function words) capped at 6."""
    return [
        w.lower() for w in text.split()
        if len(w) >= 3 and w.lower() not in _STOP_WORDS
    ][:6]


def _keyword_lyrics_search(
    query_vec: list[float],
    keywords: list[str],
    limit: int,
    artist_filter: str | None = None,
    exclude_ids: set[int] | None = None,
) -> list[dict]:
    """Keyword-filtered dense search on lyrics chunks.

    Applies a keyword AND filter (all keywords must appear in the chunk),
    then ranks the surviving chunks by cosine similarity to the query vector.
    This gives semantically best-ranked exact matches — the song that literally
    contains the queried phrase and is also closest in meaning ranks first.

    Falls back to progressively fewer keywords (drop shortest one at a time)
    if no chunks survive the filter. Tracks how many keywords were matched
    so the caller can apply stronger or weaker RRF weighting.
    """
    client = _get_client()
    if client is None or not keywords:
        return []

    from qdrant_client.models import FieldCondition, Filter, MatchText

    fetch = limit * 8

    def _run(kws: list[str]) -> list:
        text_conds = [
            FieldCondition(key="chunk_text_snippet", match=MatchText(text=w))
            for w in kws
        ]
        base = _payload_filter(artist_filter)
        must = (base.must if base else []) + text_conds
        try:
            from qdrant_client.models import SearchParams
            r = client.query_points(
                collection_name=LYRICS_COLLECTION,
                query=query_vec,
                query_filter=Filter(must=must),
                limit=fetch,
                with_payload=True,
                score_threshold=0.0,
                search_params=SearchParams(exact=True),
            )
            return r.points
        except Exception as exc:
            logger.debug("Keyword-filtered dense search error: %s", exc)
            return []

    kws = list(keywords)
    pts: list = []
    while not pts and len(kws) >= 1:
        pts = _run(kws)
        if not pts and len(kws) > 1:
            kws = sorted(kws, key=len, reverse=True)[:-1]
        else:
            break

    # Deduplicate to best-scoring chunk per song
    best: dict[int, dict] = {}
    for h in pts:
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
                "_kw_matched":    len(kws),
                "_kw_original":   len(keywords),
            }

    return sorted(best.values(), key=lambda x: x["score"], reverse=True)[:limit * 3]


def _rrf_fuse(
    dense: list[dict],
    keyword: list[dict],
    limit: int,
    k_dense: int = 60,
) -> list[dict]:
    """Merge dense and keyword result lists with asymmetric RRF.

    The keyword k is derived per-result from match precision:
      - Full AND (all N keywords matched): k_kw = 6   → ~9x stronger than dense rank-1
      - AND with N-1 keywords:             k_kw = 20
      - AND with N-2 keywords:             k_kw = 35
      - Single keyword remaining:          k_kw = 50  → similar weight to dense

    This means exact phrase matches always dominate; partial matches boost
    but don't override dense; single-word fallback barely nudges the ranking.
    """
    scores: dict[int, dict] = {}

    for rank, r in enumerate(dense, 1):
        sid = r["id"]
        scores[sid] = {
            "rrf":  1.0 / (k_dense + rank),
            "data": r,
        }

    for rank, r in enumerate(keyword, 1):
        sid = r["id"]
        # k_kw scales with how many keywords were dropped before a match was found
        matched  = r.get("_kw_matched",  1)
        original = r.get("_kw_original", 1)
        dropped  = max(0, original - matched)
        k_kw = 6 + dropped * 15          # 6 / 21 / 36 / 51 …
        kw_score = 1.0 / (k_kw + rank)

        if sid in scores:
            scores[sid]["rrf"] += kw_score
        else:
            r = dict(r)
            r["score"] = round(min(0.75, 0.45 + 0.5 / (k_kw + rank)), 4)
            scores[sid] = {"rrf": kw_score, "data": r}

    fused = sorted(scores.values(), key=lambda x: x["rrf"], reverse=True)
    # Strip internal metadata before returning
    out = []
    for item in fused[:limit]:
        d = {k: v for k, v in item["data"].items() if not k.startswith("_kw_")}
        out.append(d)
    return out


def is_available() -> bool:
    """True if Qdrant is reachable and both collections exist."""
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
    """Search the qualitative_description collection (mood / theme queries).

    Returns a list of result dicts (may be empty), or None if Qdrant is
    unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    fetch = limit + (len(exclude_ids) if exclude_ids else 0) + 5
    threshold = 0.0 if artist_filter else _SCORE_THRESHOLD
    try:
        from qdrant_client.models import SearchParams
        result = client.query_points(
            collection_name=QUALITATIVE_COLLECTION,
            query=query_vec,
            using="embedded_qualitative_description",
            limit=fetch,
            query_filter=_payload_filter(artist_filter),
            with_payload=True,
            score_threshold=threshold,
            search_params=SearchParams(exact=True),
        )
    except Exception as exc:
        logger.warning("Qdrant qualitative search error: %s", exc)
        _drop_client()
        return None

    out: list[dict] = []
    for h in result.points:
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


def search_by_title(
    query_vec: list[float],
    limit: int = 7,
    artist_filter: str | None = None,
    exclude_ids: set[int] | None = None,
) -> list[dict] | None:
    """Search the songs_qualitative collection by embedded_title vector.

    Same collection as search_qualitative but queries the embedded_title
    named vector instead of the description vector. Requires the collection
    to have been indexed with named vectors (--only-qualitative re-run).
    """
    client = _get_client()
    if client is None:
        return None

    fetch = limit + (len(exclude_ids) if exclude_ids else 0) + 5
    threshold = 0.0 if artist_filter else _SCORE_THRESHOLD
    try:
        from qdrant_client.models import SearchParams
        result = client.query_points(
            collection_name=QUALITATIVE_COLLECTION,
            query=query_vec,
            using="embedded_title",
            limit=fetch,
            query_filter=_payload_filter(artist_filter),
            with_payload=True,
            score_threshold=threshold,
            search_params=SearchParams(exact=True),
        )
    except Exception as exc:
        logger.warning("Qdrant title search error: %s", exc)
        _drop_client()
        return None

    out: list[dict] = []
    for h in result.points:
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
    limit: int = 5,
    artist_filter: str | None = None,
    exclude_ids: set[int] | None = None,
    query_text: str = "",
) -> list[dict] | None:
    """Hybrid lyrics search: dense + keyword RRF, cross-encoder reranked.

    When query_text is provided the pipeline is:
      1. Dense search with threshold=0.0 and a large fetch (limit×20) so the
         cross-encoder has full recall — the correct song must be in the pool
         even when its cosine to the query is low (synonym / paraphrase gap).
      2. Keyword-filtered dense search (AND on meaningful tokens, RRF-merged)
         to boost verbatim phrase matches that the dense model undershoots.
      3. Cross-encoder reranks the top-100 candidates by reading each
         (query, chunk) pair jointly — handles synonyms the bi-encoder misses.

    Without query_text (pure vector query, no text to rerank with):
      threshold = _SCORE_THRESHOLD, raw_limit = limit×12, no CE step.

    Returns None if Qdrant is unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    use_ce = bool(query_text)

    # With CE reranking, drop the score threshold entirely — a synonym query
    # may score below 0.28 on the bi-encoder even when it's a perfect match.
    # The CE will separate signal from noise across the full candidate pool.
    raw_limit = limit * 20 if use_ce else limit * 12
    threshold = 0.0 if (artist_filter or use_ce) else _SCORE_THRESHOLD

    # ── Dense semantic search ──────────────────────────────────────────────────
    try:
        from qdrant_client.models import SearchParams
        result = client.query_points(
            collection_name=LYRICS_COLLECTION,
            query=query_vec,
            limit=raw_limit,
            query_filter=_payload_filter(artist_filter),
            with_payload=True,
            score_threshold=threshold,
            search_params=SearchParams(exact=True),
        )
    except Exception as exc:
        logger.warning("Qdrant lyrics search error: %s", exc)
        _drop_client()
        return None

    best_dense: dict[int, dict] = {}
    for h in result.points:
        sid   = int(h.payload.get("id_lyrics", 0))
        score = float(h.score)
        if exclude_ids and sid in exclude_ids:
            continue
        if sid not in best_dense or score > best_dense[sid]["score"]:
            best_dense[sid] = {
                "id":             sid,
                "title":          str(h.payload.get("title",              "")),
                "artist":         str(h.payload.get("artist",             "")),
                "album":          str(h.payload.get("album",              "")),
                "lyrics_snippet": str(h.payload.get("chunk_text_snippet", ""))[:250],
                "score":          round(max(0.0, min(1.0, score)), 4),
            }

    dense_ranked = sorted(best_dense.values(), key=lambda x: x["score"], reverse=True)

    # ── Keyword-filtered dense search + RRF (when query_text supplied) ─────────
    ce_pool = 100  # candidates fed to the cross-encoder
    keywords = _extract_keywords(query_text) if query_text else []
    if keywords:
        kw_results = _keyword_lyrics_search(
            query_vec, keywords, limit=limit,
            artist_filter=artist_filter, exclude_ids=exclude_ids,
        )
        fused = _rrf_fuse(dense_ranked, kw_results, ce_pool if use_ce else limit * 2)
    else:
        fused = dense_ranked[:ce_pool if use_ce else limit * 2]

    # ── Cross-encoder reranking ────────────────────────────────────────────────
    if use_ce:
        logger.debug("CE reranking %d candidates for %r", len(fused), query_text[:60])
        fused = _ce_rerank(query_text, fused, ce_pool)

    # Final deduplication on (artist, title) to handle dataset duplicates
    # (same song indexed under multiple IDs).
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for r in fused:
        key = (r["artist"].lower().strip(), r["title"].lower().strip())
        if key not in seen:
            seen.add(key)
            out.append(r)
        if len(out) >= limit:
            break
    return out
