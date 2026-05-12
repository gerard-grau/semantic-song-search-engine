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
    split_words,
    tokenize,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"
_NOTICIES = _DATA_DIR / "noticies.csv"
_GRUPS    = _DATA_DIR / "grups.csv"


# Catalan stopwords that carry no retrieval signal — they would otherwise
# blow up posting-list scans (every item contains "de", "la", …) without
# adding anything to the ranking. Includes accented variants because
# normalize() keeps accents, so "més" and "mes" hash to different tokens.
_STOPWORDS = {
    # articles & per+article contractions
    "el", "la", "els", "les", "un", "una", "uns", "unes",
    "de", "del", "dels", "des", "al", "als",
    "pel", "pels",
    # prepositions
    "en", "amb", "per", "fins", "sense", "sobre", "sota",
    # conjunctions
    "i", "o", "ni",
    # interrogatives / relatives
    "que", "què", "qui", "quan", "com", "on",
    # negation / affirmation
    "no", "si", "sí",
    # clitic + tonic pronouns
    "es", "se", "ens", "us", "li", "et", "em",
    "ho", "lo", "te", "hi",
    # auxiliaries (haver, fer present tense)
    "ha", "han", "he", "has", "hem", "heu",
    "fa", "fan",
    # quantifiers & intensifiers
    "molt", "molts", "molta", "moltes",
    "tot", "tots", "tota", "totes",
    "tan", "tant", "tants", "tanta", "tantes",
    "cada", "altre", "altra", "altres",
    "gens", "res",
    # adverbs (with accented variants)
    "mes", "més", "be", "bé", "ben",
    "mai", "ja", "ara", "avui",
    "aqui", "aquí", "alla", "allà",
    "doncs",
}


# wordfreq-based dampener reference (per-million scale used by
# Parser2.load_lexicon). Each scored token is multiplied by
# 1 / (1 + lex_freq / LEX_PENALTY_REF). Set so:
#   * pel ("per+el", per-million freq ~300+) → multiplier ~0.25
#   * terra (noun, per-million freq ~50)     → multiplier ~0.67
#   * amor (noun, per-million freq ~20)      → multiplier ~0.83
#   * OOV / proper nouns / song-specific     → multiplier 1.0
# This makes "rarer words count more" hold across the language even when
# corpus IDF doesn't tell them apart (both pel and terra appear in many
# titles, but pel is grammatical filler and terra is a content noun).
LEX_PENALTY_REF = 100


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
    W_SONG_LYRICS  = 0.8
    W_GRUP_NAME    = 1.6
    W_NOTI_TITLE   = 1.6
    W_NOTI_SNIPPET = 0.4

    EXACT_PHRASE_BOOST = 50.0

    # Reconstructed-sentence exact-phrase boost. We enumerate the top
    # full-sentence reconstructions of the query (cartesian product of
    # Parser2's per-word alts, beam-pruned by joint probability) and
    # apply the same EXACT_PHRASE_BOOST to any exact match. Catches
    # "bog per tu" → "boig per tu" hitting the song title, which the
    # literal-q_norm boost misses entirely.
    RECONSTRUCT_TOP_PER_WORD   = 5     # per-word fan-out into the beam
    RECONSTRUCT_BEAM_K         = 32    # max sentences kept per beam step
    RECONSTRUCT_MIN_JOINT_PROB = 0.05  # drop reconstructions below this

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

        # Lexicon for the parser. Parser2 is lexicon-only — it does NOT
        # use catalog data for scoring. We still keep a local set of
        # catalog tokens (built below) so `derive_correction` can answer
        # "is this query word a known band/song token?" without proposing
        # a spelling fix for it.
        t0 = time.time()
        try:
            self.parser.load_lexicon(min_zipf=2.4)
        except Exception as exc:  # wordfreq not installed → degrade gracefully
            logger.warning("[cercador] lexicon unavailable: %s", exc)
        self.catalog_tokens: set[str] = set()
        for s in self.songs:
            self.catalog_tokens.update(tokenize(normalize(s.get("title", ""))))
            self.catalog_tokens.update(tokenize(normalize(s.get("artist", ""))))
        for g in self.grups:
            self.catalog_tokens.update(tokenize(normalize(g.get("name", ""))))
        for n in self.noticies:
            self.catalog_tokens.update(tokenize(normalize(n.get("title", ""))))
        logger.info(
            "[cercador] parser ready in %.1fs (%d catalog tokens)",
            time.time() - t0, len(self.catalog_tokens),
        )

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

            # Short fields (title, artist) are indexed *including* stopwords
            # so an all-stopwords query like "pel" can still surface "Pel
            # Cami" via the fallback in search(). Stopwords are filtered at
            # query time in _score, except when every input token is a
            # stopword — there's no budget concern on short fields.
            for tok in set(tokenize(title)):
                self.songs_idx[tok].append((i, self.W_SONG_TITLE))
            for tok in set(tokenize(artist)):
                self.songs_idx[tok].append((i, self.W_SONG_ARTIST))
            # Snippet keeps the stopword filter: 25-token budget per song
            # would otherwise be eaten by "de"/"la" and starve real signal.
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

        # When every input token is a stopword ("pel", "el meu", …) the
        # standard filter blocks every candidate and we'd return nothing.
        # Score with stopwords enabled in that case — the lex_penalty and
        # BM25 IDF already crush low-signal tokens, so rankings stay sane
        # (matches on rarer stopwords like "pel" outrank near-universal
        # ones like "el", and titles with multiple stopword hits rise).
        q_tokens = tokenize(q_norm)
        keep_stopwords = bool(q_tokens) and all(t in _STOPWORDS for t in q_tokens)
        fw = not keep_stopwords

        grup_scores    = self._score(parsed, self.grups_idx,    len(self.grups),    filter_stopwords=fw)
        song_scores    = self._score(parsed, self.songs_idx,    len(self.songs),    filter_stopwords=fw)
        noticia_scores = self._score(parsed, self.noticies_idx, len(self.noticies), filter_stopwords=fw)

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

        # Reconstruction-based exact-phrase boost. Same EXACT_PHRASE_BOOST
        # for any reconstruction that exact-matches a phrase index — the
        # joint-probability floor inside _enumerate_reconstructions has
        # already gated which combinations are "high enough probability"
        # to consider, so survivors all deserve the full boost.
        for phrase, _jp in self._enumerate_reconstructions(query):
            if phrase == q_norm:
                continue  # already covered by the literal-q_norm pass above
            for i in self.grups_phrase.get(phrase, ()):
                grup_scores[i] += self.EXACT_PHRASE_BOOST
            for i in self.songs_title_phrase.get(phrase, ()):
                song_scores[i] += self.EXACT_PHRASE_BOOST
            for i in self.songs_artist_phrase.get(phrase, ()):
                song_scores[i] += self.EXACT_PHRASE_BOOST * 0.5
            for i in self.noticies_phrase.get(phrase, ()):
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

        # Dedup keys are normalized so casing/accent variants of the same
        # record collapse: "Sau" and "sau" → one group, etc.
        return {
            "grups": self._top(
                grup_scores, self.grups, top_grups,
                dedup_key=lambda g: normalize(g.get("name", "")),
            ),
            "cancons": self._top(
                song_scores, self.songs, top_songs,
                dedup_key=lambda s: (
                    normalize(s.get("title", "")),
                    normalize(s.get("artist", "")),
                ),
            ),
            "noticies": self._top(
                noticia_scores, self.noticies, top_noticies,
                dedup_key=lambda n: (
                    normalize(n.get("title", "")),
                    n.get("date", ""),
                ),
            ),
            "parsed": parsed,
        }

    def _enumerate_reconstructions(self, query: str) -> list[tuple[str, float]]:
        """
        Top full-sentence reconstructions of `query`, ranked by joint
        per-word probability. Beam-searches over Parser2's per-word
        distributions so a query like "bog per tu" yields
        ("boig per tu", 0.85), ("bog per tu", 0.10), ...

        Positions are aligned with split_words(q_norm), which keeps
        single-char words like the Catalan conjunction "i" that
        tokenize() filters out. Those short positions are pinned to a
        {word: 1.0} singleton (Parser2 doesn't score them) so the
        reconstruction preserves them verbatim — without this, the
        phrase key "com el dia i la nit" can never be exact-matched
        from a query like "comel dia i lanit", where "i" would
        otherwise be dropped before the beam ever ran.

        The beam holds (phrase, log_prob) so joint = product of per-word
        probs stays numerically stable on long queries. Width is
        RECONSTRUCT_BEAM_K — that's the budget on full sentences we'll
        bother to exact-match. Per-word fan-out is capped at
        RECONSTRUCT_TOP_PER_WORD so a noisy distribution can't blow up
        the beam in a single step. Reconstructions whose joint
        probability falls below RECONSTRUCT_MIN_JOINT_PROB are dropped
        before returning — that's the "high enough probability" gate.

        Output phrases are already normalised (parser2 candidates come
        from a normalised lexicon plus the input itself, which the
        parser normalises at parse time), so callers can use them as
        keys into the *_phrase indices directly.
        """
        all_words = split_words(normalize(query))
        if not all_words:
            return []
        # split_words preserves single-char positions; parse_per_word
        # only produces distributions for ≥2-char tokens, so zip them
        # together with a fixed singleton at every short position.
        per_word = iter(self.parser.parse_per_word(query))
        distributions: list[dict[str, float]] = [
            next(per_word) if len(w) >= 2 else {w: 1.0}
            for w in all_words
        ]
        # Beam: list of (phrase, log_prob). Seed with the empty prefix
        # at log_prob = 0, then expand one word position at a time.
        beam: list[tuple[str, float]] = [("", 0.0)]
        for dist in distributions:
            top_alts = sorted(dist.items(), key=lambda kv: -kv[1])[
                : self.RECONSTRUCT_TOP_PER_WORD
            ]
            next_beam: list[tuple[str, float]] = []
            for phrase, lp in beam:
                for cand, p in top_alts:
                    if p <= 0.0:
                        continue
                    new_phrase = f"{phrase} {cand}" if phrase else cand
                    next_beam.append((new_phrase, lp + math.log(p)))
            next_beam.sort(key=lambda x: -x[1])
            beam = next_beam[: self.RECONSTRUCT_BEAM_K]
        floor = self.RECONSTRUCT_MIN_JOINT_PROB
        return [
            (phrase, jp)
            for phrase, lp in beam
            for jp in (math.exp(lp),)
            if jp >= floor
        ]

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

    def _score(
        self,
        parsed: dict[str, float],
        idx: dict[str, list[tuple[int, float]]],
        n_items: int,
        filter_stopwords: bool = True,
    ) -> dict[int, float]:
        """
        Token scoring: per posting, add ``prob * idf * lex_penalty *
        field_weight`` to the item's score.

        IDF uses BM25's classical form, ``log((N - df + 0.5) / (df + 0.5))``,
        clamped to a 0.1 floor. Drops sharply once a term sits in more than
        ~30% of docs (and would go negative past ~50% without the clamp),
        so function words that flood the catalog stop dominating the score
        — while a near-universal token still nudges multi-word matches
        above single-token ones (we don't hard-cut: "bog per tu" relies on
        "tu"'s small IDF to rank "Boig per Tu" above lone rare-token noise
        like "Mr Bong").

        Lex penalty knocks down candidates that wordfreq considers very
        common Catalan, regardless of corpus df. Catches function words
        like ``pel`` (per+el) even when they don't dominate the catalog
        statistically, and lets a rare noun beat a common-noun match of
        the same df — which corpus IDF alone can't do.
        """
        scores: dict[int, float] = defaultdict(float)
        if not n_items:
            return scores
        lex = self.parser.lexicon
        for tok, prob in parsed.items():
            if len(tok) < 2:
                continue
            if filter_stopwords and tok in _STOPWORDS:
                continue
            postings = idx.get(tok)
            if not postings:
                continue
            df = len(postings)
            idf = max(0.1, math.log((n_items - df + 0.5) / (df + 0.5)))
            lex_penalty = 1.0 / (1.0 + lex.get(tok, 0) / LEX_PENALTY_REF)
            weight = prob * idf * lex_penalty
            for item_idx, field_w in postings:
                scores[item_idx] += weight * field_w
        return scores

    @staticmethod
    def _top(
        scores: dict[int, float],
        items: list[dict],
        k: int,
        dedup_key=None,
    ) -> list[dict]:
        """
        Top-k by score, with optional dedup by a caller-supplied key. Source
        lists have logical duplicates (augmented_songs has repeated id_lyrics
        rows; grups/noticies CSVs aren't unique on name/title) so the same
        record can sit at several indices, each scored independently. We sort
        all of them, then walk in score order keeping the first occurrence
        per dedup key — guarantees k *distinct* results when available.
        """
        if not scores:
            return []
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        if dedup_key is None:
            return [items[i] for i, _ in ranked[:k]]
        out: list[dict] = []
        seen: set = set()
        for i, _ in ranked:
            item = items[i]
            key = dedup_key(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
            if len(out) >= k:
                break
        return out


# ---------------------------------------------------------------------------
# Correction UX (frontend expects {corrected, suggestions})
# ---------------------------------------------------------------------------

def derive_correction(
    query: str,
    parsed: dict[str, float],
    index: "CercadorIndex",
    min_alt_prob: float = 0.6,
    lexicon_freq_floor: int = 200,
) -> dict | None:
    """
    Reverse-engineer a per-word correction string from Parser2's
    output. We only propose a fix for words that are NOT in the catalog
    AND NOT a common Catalan word — otherwise every correctly typed
    query would be "corrected" to its nearest one-edit neighbour
    ("boig per tu" → "goig pre tú").

    catalog_tokens lives on the index now (parser2 is lexicon-only).
    """
    q_norm = normalize(query)
    input_words = tokenize(q_norm)
    if not input_words:
        return None
    input_set = set(input_words)
    catalog_tokens = index.catalog_tokens
    lexicon = index.parser.lexicon

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
            # Skip pair-of-words candidates ("molt be") — they're useful
            # for retrieval but not for per-word correction.
            if " " in cand:
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
