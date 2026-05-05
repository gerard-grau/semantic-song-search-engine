"""
Cercador retrieval — inverted indices over the real CSV data.

Sources:
  * songs    — load_all_songs() (augmented_songs.csv ⨝ cancons.csv,
               restricted to IDs present in embedded_songs.parquet so that
               clicking a result can resolve to a SongDetail).
  * grups    — grups.csv
  * noticies — noticies.csv

Pipeline:
  1. Parser2 expands the user query into a {token: probability} bag.
  2. For each (token, prob) we look up posting lists in three inverted
     indices (one per source) and accumulate score = prob * idf * field_w.
  3. Exact-phrase hits get a large additive boost so an artist named
     exactly "Sau" surfaces above a song that contains the word "sau".
  4. Top-K per source is returned.

Indices and the parser share a process-lifetime singleton built lazily
on the first /api/cercador call (or eagerly via :func:`prewarm`).
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

from app.backend.core.data_loader import load_all_songs
from app.backend.core.parser2 import (
    MAX_PHRASE_DISTANCE,
    MAX_WORD_DISTANCE,
    Parser2,
    distance_to_prob,
    edit_distance,
    normalize,
    tokenize,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"
_NOTICIES = _DATA_DIR / "noticies.csv"
_GRUPS    = _DATA_DIR / "grups.csv"


# Catalan stopwords that carry no retrieval signal — they would otherwise
# blow up posting-list scans (every item contains "de", "la", …) without
# adding anything to the ranking. Parser2 already down-weights common
# inputs, but the IDF in scoring would still leak score through them.
_STOPWORDS = {
    "el", "la", "els", "les", "un", "una", "uns", "unes",
    "de", "del", "dels", "des", "al", "als", "en", "amb", "per",
    "que", "qui", "i", "o", "no", "si",
    "es", "se", "ens", "us", "li", "et", "em",
    "ha", "han", "he", "fa",
    "mes", "be", "mai", "aqui", "alla", "avui", "ara", "com",
    "molt", "tot", "tots", "cada", "quan", "on",
    "ho", "lo", "te", "del",
}


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------

def _safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    return "" if s in ("nan", "NaN", "None") else s


def _load_grups() -> list[dict]:
    if not _GRUPS.exists():
        logger.warning("grups.csv not found at %s", _GRUPS)
        return []
    df = pd.read_csv(
        _GRUPS,
        usecols=["id_grup", "nom", "num_cancons", "viasona_link",
                 "foto", "municipi", "regio"],
        dtype={"id_grup": "Int64", "num_cancons": "Int64"},
    )
    out: list[dict] = []
    for _, row in df.iterrows():
        name = _safe_str(row.get("nom"))
        if not name:
            continue
        out.append({
            "id":           int(row["id_grup"]) if pd.notna(row["id_grup"]) else 0,
            "name":         name,
            "song_count":   int(row["num_cancons"]) if pd.notna(row.get("num_cancons")) else 0,
            "viasona_link": _safe_str(row.get("viasona_link")),
            "foto":         _safe_str(row.get("foto")),
            "municipi":     _safe_str(row.get("municipi")),
            "regio":        _safe_str(row.get("regio")),
            "genres":       [],
        })
    out.sort(key=lambda g: g["name"])
    return out


def _load_noticies() -> list[dict]:
    if not _NOTICIES.exists():
        logger.warning("noticies.csv not found at %s", _NOTICIES)
        return []
    df = pd.read_csv(
        _NOTICIES,
        usecols=["id_article", "titol", "subtitol", "entrada",
                 "data", "viasona_link"],
        dtype={"id_article": "Int64"},
    )
    out: list[dict] = []
    for _, row in df.iterrows():
        title = _safe_str(row.get("titol"))
        if not title:
            continue
        snippet = _safe_str(row.get("entrada")) or _safe_str(row.get("subtitol"))
        out.append({
            "id":           int(row["id_article"]) if pd.notna(row["id_article"]) else 0,
            "title":        title,
            "subtitol":     _safe_str(row.get("subtitol")),
            "date":         _safe_str(row.get("data"))[:10],
            "snippet":      snippet[:300],
            "viasona_link": _safe_str(row.get("viasona_link")),
        })
    return out


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

class CercadorIndex:
    """In-memory inverted indices over songs/grups/noticies."""

    # Field weights — title/name fields beat snippets/lyrics. Exact-phrase
    # match on the whole field gets an additive boost on top.
    W_SONG_TITLE   = 1.6
    W_SONG_ARTIST  = 1.3
    W_SONG_LYRICS  = 0.4
    W_GRUP_NAME    = 1.6
    W_NOTI_TITLE   = 1.6
    W_NOTI_SNIPPET = 0.4

    EXACT_PHRASE_BOOST = 50.0

    def __init__(self):
        self.songs:    list[dict] = []
        self.grups:    list[dict] = []
        self.noticies: list[dict] = []

        self.songs_idx:    dict[str, list[tuple[int, float]]] = defaultdict(list)
        self.grups_idx:    dict[str, list[tuple[int, float]]] = defaultdict(list)
        self.noticies_idx: dict[str, list[tuple[int, float]]] = defaultdict(list)

        # Full normalized phrase → list of indices, used for exact-match boosts.
        self.songs_title_phrase:    dict[str, list[int]] = defaultdict(list)
        self.songs_artist_phrase:   dict[str, list[int]] = defaultdict(list)
        self.grups_phrase:          dict[str, list[int]] = defaultdict(list)
        self.noticies_phrase:       dict[str, list[int]] = defaultdict(list)

        # Per-index normalized phrase, for the phrase-edit-distance rerank
        # step. Storing them as parallel lists rather than recomputing on
        # the hot path saves a normalize() per item per query.
        self._songs_title_norm:    list[str] = []
        self._songs_artist_norm:   list[str] = []
        self._grups_name_norm:     list[str] = []
        self._noticies_title_norm: list[str] = []

        self.parser = Parser2()
        self._built = False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> None:
        if self._built:
            return

        t0 = time.time()
        self.songs    = load_all_songs()
        self.grups    = _load_grups()
        self.noticies = _load_noticies()
        logger.info(
            "[cercador] loaded %d songs, %d grups, %d noticies in %.1fs",
            len(self.songs), len(self.grups), len(self.noticies), time.time() - t0,
        )

        # Catalog for the parser: every unique title + artist + grup name +
        # noticia title. Parser2 dedupes internally.
        t0 = time.time()
        catalog_entries: list[dict] = []
        for s in self.songs:
            catalog_entries.append({"title": s.get("title", ""), "artist": s.get("artist", "")})
        for g in self.grups:
            catalog_entries.append({"title": "", "artist": g["name"]})
        for n in self.noticies:
            catalog_entries.append({"title": n["title"], "artist": ""})
        self.parser.load_catalog(catalog_entries)
        try:
            self.parser.load_lexicon(min_zipf=2.4)
        except Exception as exc:  # wordfreq not installed → degrade gracefully
            logger.warning("[cercador] lexicon unavailable: %s", exc)
        logger.info("[cercador] parser ready in %.1fs", time.time() - t0)

        # Build inverted indices.
        t0 = time.time()
        self._index_songs()
        self._index_grups()
        self._index_noticies()
        logger.info("[cercador] inverted indices built in %.1fs", time.time() - t0)

        self._built = True

    def _index_songs(self) -> None:
        self._songs_title_norm  = [""] * len(self.songs)
        self._songs_artist_norm = [""] * len(self.songs)
        for i, s in enumerate(self.songs):
            title  = normalize(s.get("title", ""))
            artist = normalize(s.get("artist", ""))
            self._songs_title_norm[i]  = title
            self._songs_artist_norm[i] = artist
            if title:
                self.songs_title_phrase[title].append(i)
            if artist:
                self.songs_artist_phrase[artist].append(i)

            # Tokens come from the normalized field. Use a per-field set so
            # repeated tokens don't double-count weight.
            for tok in set(tokenize(title)):
                if tok not in _STOPWORDS:
                    self.songs_idx[tok].append((i, self.W_SONG_TITLE))
            for tok in set(tokenize(artist)):
                if tok not in _STOPWORDS:
                    self.songs_idx[tok].append((i, self.W_SONG_ARTIST))
            # Snippet: index a few high-information tokens to support
            # lyric-style queries without ballooning the index.
            snippet = normalize(s.get("lyrics_snippet", "")[:200])
            seen: set[str] = set()
            for tok in tokenize(snippet):
                if tok in _STOPWORDS or tok in seen:
                    continue
                seen.add(tok)
                self.songs_idx[tok].append((i, self.W_SONG_LYRICS))
                if len(seen) >= 25:
                    break

    def _index_grups(self) -> None:
        self._grups_name_norm = [""] * len(self.grups)
        for i, g in enumerate(self.grups):
            name = normalize(g["name"])
            self._grups_name_norm[i] = name
            if name:
                self.grups_phrase[name].append(i)
            for tok in set(tokenize(name)):
                if tok not in _STOPWORDS:
                    self.grups_idx[tok].append((i, self.W_GRUP_NAME))

    def _index_noticies(self) -> None:
        self._noticies_title_norm = [""] * len(self.noticies)
        for i, n in enumerate(self.noticies):
            title   = normalize(n["title"])
            snippet = normalize(n.get("snippet", "")[:200])
            self._noticies_title_norm[i] = title
            if title:
                self.noticies_phrase[title].append(i)
            for tok in set(tokenize(title)):
                if tok not in _STOPWORDS:
                    self.noticies_idx[tok].append((i, self.W_NOTI_TITLE))
            seen: set[str] = set()
            for tok in tokenize(snippet):
                if tok in _STOPWORDS or tok in seen:
                    continue
                seen.add(tok)
                self.noticies_idx[tok].append((i, self.W_NOTI_SNIPPET))
                if len(seen) >= 25:
                    break

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_grups: int = 5,
        top_songs: int = 8,
        top_noticies: int = 5,
    ) -> dict:
        # phrase_match=False: Parser2's full-query phrase scan is O(catalog)
        # and dominates latency. Our inverted index already retrieves multi-
        # word matches; we just need bag-of-words query expansion (input
        # words + per-word fuzzy alternates) from the parser.
        parsed = self.parser.parse(query, top_k=20, phrase_match=False)
        q_norm = normalize(query)

        grup_scores    = self._score(parsed, self.grups_idx,    len(self.grups))
        song_scores    = self._score(parsed, self.songs_idx,    len(self.songs))
        noticia_scores = self._score(parsed, self.noticies_idx, len(self.noticies))

        # Exact-phrase boosts so "Sau" → the band Sau, not a song with "sau"
        # buried in lyrics. We boost each matching index, not all-or-nothing.
        for i in self.grups_phrase.get(q_norm, ()):
            grup_scores[i] += self.EXACT_PHRASE_BOOST
        for i in self.songs_title_phrase.get(q_norm, ()):
            song_scores[i] += self.EXACT_PHRASE_BOOST
        for i in self.songs_artist_phrase.get(q_norm, ()):
            song_scores[i] += self.EXACT_PHRASE_BOOST * 0.5
        for i in self.noticies_phrase.get(q_norm, ()):
            noticia_scores[i] += self.EXACT_PHRASE_BOOST

        # Phrase-edit-distance rerank over the top candidates of each
        # collection. This recovers the signal Parser2's _phrase_match used
        # to provide (e.g. "bog per tu" boosting "boig per tu" specifically),
        # but bounded — we only score the top ~120 candidates rather than
        # the entire catalog. Only fires for multi-token queries: for a
        # single-token input the user almost always wants matches *containing*
        # that token (e.g. "sau" → song "Sau Pans"), not phrases of similar
        # *total length* — and a full-phrase edit distance would wrongly
        # promote short same-length phrases like "Suau".
        if len(tokenize(q_norm)) >= 2:
            ql = len(q_norm)
            self._phrase_rerank(q_norm, ql, song_scores, self._songs_title_norm,
                                top_n=120, weight=18.0)
            self._phrase_rerank(q_norm, ql, song_scores, self._songs_artist_norm,
                                top_n=120, weight=12.0)
            self._phrase_rerank(q_norm, ql, grup_scores, self._grups_name_norm,
                                top_n=120, weight=18.0)
            self._phrase_rerank(q_norm, ql, noticia_scores, self._noticies_title_norm,
                                top_n=120, weight=12.0)

        return {
            "grups":    self._top(grup_scores,    self.grups,    top_grups),
            "cancons":  self._top(song_scores,    self.songs,    top_songs),
            "noticies": self._top(noticia_scores, self.noticies, top_noticies),
            "parsed":   parsed,
        }

    @staticmethod
    def _phrase_rerank(
        query: str,
        ql: int,
        scores: dict[int, float],
        norm_phrases: list[str],
        top_n: int,
        weight: float,
    ) -> None:
        """
        Pull the top ``top_n`` candidates from ``scores`` and add a phrase-
        level edit-distance bonus. Bounded by ``top_n`` so the rerank is
        independent of catalog size — typically ~5 ms for top_n=120.
        """
        if not scores:
            return
        candidates = sorted(scores.items(), key=lambda kv: -kv[1])[:top_n]
        max_d = MAX_PHRASE_DISTANCE
        for idx, _ in candidates:
            phrase = norm_phrases[idx] if idx < len(norm_phrases) else ""
            if not phrase:
                continue
            # Length-prefilter: DL distance ≥ |Δlen| under unit costs, and
            # our space cost is 2.0, so a wide length gap is hopeless.
            if abs(len(phrase) - ql) > max_d:
                continue
            d = edit_distance(query, phrase, cap=max_d)
            if d > max_d:
                continue
            scores[idx] += distance_to_prob(d, max(ql, len(phrase))) * weight

    @staticmethod
    def _score(
        parsed: dict[str, float],
        idx: dict[str, list[tuple[int, float]]],
        n_items: int,
    ) -> dict[int, float]:
        """
        Token scoring: per posting, add ``prob * idf * field_weight`` to the
        item's score. We do *not* hard-cut high-df tokens — that previously
        dropped useful signal (a query like "bog per tu" relies on "tu"'s
        low-but-nonzero IDF to rank the song "Boig per Tu" above a single-
        rare-token distractor like "Mr Bong"). IDF naturally squashes the
        most common tokens; we just clamp it to a small floor so a near-
        universal token still nudges multi-word matches above single-token
        ones without dominating the ranking.
        """
        scores: dict[int, float] = defaultdict(float)
        if not n_items:
            return scores
        log_n = math.log(1 + n_items)
        for tok, prob in parsed.items():
            if len(tok) < 2 or tok in _STOPWORDS:
                continue
            postings = idx.get(tok)
            if not postings:
                continue
            df = len(postings)
            idf = max(0.1, log_n - math.log(df))
            weight = prob * idf
            for item_idx, field_w in postings:
                scores[item_idx] += weight * field_w
        return scores

    @staticmethod
    def _top(
        scores: dict[int, float],
        items: list[dict],
        k: int,
    ) -> list[dict]:
        if not scores:
            return []
        # Cheap top-k: sort once. For the catalog sizes here (≤ 1 M) this is
        # well under a millisecond on hot scores.
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        return [items[i] for i, _ in ranked]


# ---------------------------------------------------------------------------
# Correction UX (frontend expects {corrected, suggestions})
# ---------------------------------------------------------------------------

def derive_correction(
    query: str,
    parsed: dict[str, float],
    parser: "Parser2",
    min_alt_prob: float = 0.6,
    lexicon_freq_floor: int = 200,
) -> dict | None:
    """
    Reverse-engineer a per-word correction string from Parser2's bag-of-
    words output. We only propose a fix for words that are NOT in the
    catalog and NOT a common Catalan word — otherwise every correctly
    typed query would be "corrected" to its nearest one-edit neighbour
    ("boig per tu" → "goig pre tú").
    """
    q_norm = normalize(query)
    input_words = tokenize(q_norm)
    if not input_words:
        return None
    input_set = set(input_words)
    catalog_tokens = parser.catalog_tokens
    lexicon = parser.lexicon

    def _word_is_known(w: str) -> bool:
        if w in catalog_tokens:
            return True
        return lexicon.get(w, 0) >= lexicon_freq_floor

    per_word_alts: list[list[tuple[str, float]]] = []
    for w in input_words:
        if _word_is_known(w) or len(w) <= 2:
            per_word_alts.append([])
            continue
        alts: list[tuple[str, float]] = []
        for cand, prob in parsed.items():
            if cand == w or cand in input_set:
                continue
            d = edit_distance(w, cand, cap=MAX_WORD_DISTANCE)
            if 0 < d <= MAX_WORD_DISTANCE:
                alts.append((cand, prob))
        alts.sort(key=lambda x: -x[1])
        per_word_alts.append(alts[:3])

    corrected_words: list[str] = []
    has_change = False
    for w, alts in zip(input_words, per_word_alts):
        if alts and alts[0][1] >= min_alt_prob:
            corrected_words.append(alts[0][0])
            has_change = True
        else:
            corrected_words.append(w)
    if not has_change:
        return None

    corrected = " ".join(corrected_words)

    # Alternative phrasings: pick the next-best alt for each word that has
    # one, build a phrase, dedupe.
    suggestions: list[str] = []
    for k in (1, 2):
        alt_words: list[str] = []
        differs = False
        for (w, alts), corrected_w in zip(zip(input_words, per_word_alts), corrected_words):
            if k < len(alts) and alts[k][1] >= min_alt_prob - 0.15:
                alt_words.append(alts[k][0])
                if alts[k][0] != corrected_w:
                    differs = True
            else:
                alt_words.append(corrected_w)
        s = " ".join(alt_words)
        if differs and s != corrected and s not in suggestions:
            suggestions.append(s)

    return {"corrected": corrected, "suggestions": suggestions}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_INDEX: CercadorIndex | None = None


def get_index() -> CercadorIndex:
    """Process-lifetime singleton; builds on first call."""
    global _INDEX
    if _INDEX is None:
        idx = CercadorIndex()
        idx.build()
        _INDEX = idx
    return _INDEX


def prewarm() -> None:
    """Build the index ahead of the first request (called from main.lifespan)."""
    get_index()
