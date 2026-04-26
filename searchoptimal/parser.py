"""
Catalan song-search query parser.

Two-stage pipeline — Google "Did you mean / autocomplete" style:

    1. TRIVIAL NORMALISATION
       case, NFC, smart-quote → ASCII, l·l typo patterns, triple-letter
       collapse. Fast and always applied.

    2. PHRASE-LEVEL CORRECTION & COMPLETION
       The query is matched as a WHOLE against a database of song titles
       and artist names. We try four phrase strategies in parallel:

         a) exact or fuzzy phrase match (artist / title)
         b) prefix completion        ("boig per"  → "boig per tu")
         c) artist|title split       ("sau boig per tu")
         d) artist → song expansion  ("lluís llach" → "lluís llach l'estaca")

       All phrase candidates carry an edit distance and a tier weight.

    3. TOKEN-LEVEL FALLBACK  (only if no confident phrase match)
       Per-token lexicon lookup for lyric-style queries.
       This never clobbers a good phrase match — the guard is up-front.

Scoring
-------
Every candidate has (text, distance, tier, freq):

    score = tier * 10_000 − distance * 100 + log1p(freq)

Tiers:
    ARTIST_PHRASE      = 12    exact/fuzzy match vs an artist name
    TITLE_PHRASE       = 11    exact/fuzzy match vs a title
    SPLIT_PHRASE       = 11    artist|title joint match
    COMPLETION_ARTIST  = 11    query is a prefix of an artist
    COMPLETION_TITLE   = 10    query is a prefix of a title
    ARTIST_TOKEN       = 4     per-token artist match
    TITLE_TOKEN        = 3     per-token title match
    LEXICON            = 1     generic Catalan word (wordfreq)

With tier * 10k the coefficient difference is huge: an artist-phrase
match at distance 4 (120 000 − 400 ≈ 119 600) still beats a perfect
lexicon correction (10 000). That is "weight titles and authors MUCH more".

Accent-insensitivity is free: every index is mirrored by an accent-folded
twin, so "cancio" → "cançó" is a zero-cost correction.
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from dataclasses import dataclass
from symspellpy import SymSpell, Verbosity


# ---------------------------------------------------------------------------
# Language resources
# ---------------------------------------------------------------------------

ESSENTIAL_WORDS = {
    'el', 'la', 'els', 'les', 'un', 'una', 'uns', 'unes',
    'de', 'del', 'dels', 'a', 'al', 'als', 'en', 'amb', 'per',
    'que', 'què', 'qui', 'i', 'o', 'no', 'si', 'sí',
    'jo', 'tu', 'ell', 'ella', 'nosaltres', 'vosaltres', 'ells', 'elles',
    'em', 'et', 'es', 'se', 'ens', 'us', 'li',
    'meu', 'teu', 'seu', 'meva', 'teva', 'seva',
    'és', 'ha', 'han', 'he', 'fa', 'ser',
    'més', 'bé', 'mai', 'aquí', 'allà', 'avui', 'ara', 'com',
    'molt', 'tot', 'tots', 'cada', 'quan', 'on',
}

LEXICON_BLACKLIST = {'canco', 'cancons', 'mes'}

NORMALIZE_PATTERNS = [
    (re.compile(r'(?<=[a-zà-ú])l[.\-]l(?=[a-zà-ú])', re.IGNORECASE), 'l·l'),
    (re.compile(r'(.)\1{2,}'), r'\1\1'),
]

TOKEN_RE = re.compile(r"[a-zàèéíòóúïüç]+(?:·[a-zàèéíòóúïüç]+)*", re.IGNORECASE)
CONTRACTION_RE = re.compile(r"([ldsmtn])'", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------

TIER_ARTIST_PHRASE     = 12
TIER_TITLE_PHRASE      = 11
TIER_SPLIT_PHRASE      = 11
TIER_COMPLETION_ARTIST = 11
TIER_COMPLETION_TITLE  = 10
TIER_EXPANSION         = 9   # artist → "artist + song" suggestion
TIER_ARTIST_TOKEN      = 4
TIER_TITLE_TOKEN       = 3
TIER_LEXICON           = 1

# Suggestions outside this score gap below the top candidate are dropped.
# One tier level is worth 10 000; 25 000 tolerates artist→song expansions
# (tier 9) as suggestions for a phrase-tier winner (tier 11), while still
# rejecting lexicon-tier noise below a phrase winner.
SUGGESTION_SCORE_GAP = 25_000

MAX_ED_PHRASE = 4
MAX_ED_TOKEN  = 2
MIN_TOKEN_LEN_FOR_CORRECTION = 3

# Minimum lexicon frequency a segmentation part must have. Anything below
# this is corpus noise (e.g. proper-noun fragments that happen to appear
# once in wordfreq) and should not justify breaking a longer string apart.
MIN_SEGMENT_PART_FREQ = 10

# Word-weight threshold — words below this aren't included in the output
# bag. 0.30 keeps tokens from suggestions one tier below the winner but
# rejects raw lexicon-tier noise.
MIN_WORD_WEIGHT = 0.30
ORIGINAL_WORD_WEIGHT = 0.50

FREQ_ARTIST_TOKEN = 100_000
FREQ_TITLE_TOKEN  = 20_000
FREQ_PHRASE       = 1_000_000


def adaptive_max_ed(text_len: int, cap: int = 4) -> int:
    """
    Edit-distance budget that scales with input length. A 2-letter word
    can't tolerate 1 edit (50% wrong); a 15-letter word at d=3 (20%
    wrong) usually still means the same word.
    """
    if text_len <= 3:
        ed = 0
    elif text_len <= 5:
        ed = 1
    elif text_len <= 9:
        ed = 2
    elif text_len <= 13:
        ed = 3
    else:
        ed = 4
    return min(ed, cap)


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    text: str
    distance: int
    tier: int
    freq: int = 1
    tier_name: str = ''

    @property
    def score(self) -> float:
        return self.tier * 10_000.0 - self.distance * 100.0 + math.log1p(self.freq)


# ---------------------------------------------------------------------------
# Normalisation (pure)
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    text = unicodedata.normalize('NFC', text)
    text = text.lower().strip()
    text = text.replace('’', "'").replace('‘', "'").replace('´', "'")
    for pattern, repl in NORMALIZE_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def fold_accents(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text)
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.replace('ç', 'c').replace('·', '')


def tokenize(text: str) -> list[str]:
    expanded = CONTRACTION_RE.sub(r'\1 ', text)
    toks = TOKEN_RE.findall(expanded)
    return [t for t in toks if len(t) >= 2 or t in ESSENTIAL_WORDS]


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                curr[j] + 1,          # insert
                prev[j + 1] + 1,      # delete
                prev[j] + (ca != cb), # substitute
            ))
        prev = curr
    return prev[-1]


# ---------------------------------------------------------------------------
# Dual-SymSpell index (accented + accent-folded, kept in sync)
# ---------------------------------------------------------------------------

class _Index:
    def __init__(self, max_ed: int, prefix_length: int = 7):
        self.sym        = SymSpell(max_ed, prefix_length=prefix_length)
        self.sym_folded = SymSpell(max_ed, prefix_length=prefix_length)
        self.fold_map: dict[str, str] = {}
        self._freq: dict[str, int] = {}

    def add(self, text: str, freq: int) -> None:
        if not text:
            return
        self._freq[text] = self._freq.get(text, 0) + freq
        self.sym.create_dictionary_entry(text, self._freq[text])
        folded = fold_accents(text)
        self.sym_folded.create_dictionary_entry(folded, self._freq[text])
        prev = self.fold_map.get(folded)
        if prev is None or self._freq.get(prev, 0) < self._freq[text]:
            self.fold_map[folded] = text

    def contains(self, text: str) -> bool:
        return text in self._freq

    def freq(self, text: str) -> int:
        return self._freq.get(text, 0)

    def entries(self):
        return self._freq.keys()

    def lookup(self, text: str, tier: int, max_ed: int, tier_name: str = '',
               verbosity: Verbosity = Verbosity.CLOSEST) -> list[Candidate]:
        out: list[Candidate] = []
        for s in self.sym_folded.lookup(fold_accents(text), verbosity,
                                        max_edit_distance=max_ed):
            restored = self.fold_map.get(s.term, s.term)
            out.append(Candidate(restored, s.distance, tier, s.count,
                                 tier_name=tier_name))
        for s in self.sym.lookup(text, verbosity, max_edit_distance=max_ed):
            out.append(Candidate(s.term, s.distance, tier, s.count,
                                 tier_name=tier_name))
        return out


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class CatalanSongQueryParser:

    def __init__(self, max_edit_distance: int = MAX_ED_PHRASE):
        self.max_edit_distance = max_edit_distance

        self.artist_phrase = _Index(max_edit_distance, prefix_length=10)
        self.title_phrase  = _Index(max_edit_distance, prefix_length=10)
        self.artist_token  = _Index(MAX_ED_TOKEN)
        self.title_token   = _Index(MAX_ED_TOKEN)
        self.lexicon       = _Index(MAX_ED_TOKEN)

        # Canonical display forms: normalised → original-cased string.
        self.title_display:  dict[str, str] = {}
        self.artist_display: dict[str, str] = {}

        # Who owns which songs — used for artist→song expansion suggestions.
        self.songs_by_artist: dict[str, list[str]] = {}

        self._seg: SymSpell | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_lexicon(self, min_zipf: float = 2.4, top_n: int = 100_000) -> None:
        """Populate the generic Catalan lexicon from wordfreq."""
        try:
            from wordfreq import top_n_list, zipf_frequency, word_frequency
        except ImportError as e:
            raise RuntimeError("wordfreq is required: pip install wordfreq") from e

        loaded = 0
        for word in top_n_list('ca', top_n):
            if zipf_frequency(word, 'ca') < min_zipf:
                continue
            word = word.strip().lower()
            if len(word) < 2 or word in LEXICON_BLACKLIST:
                continue
            if not re.search(r'[a-zàèéíòóúïüç]', word):
                continue
            count = max(1, int(word_frequency(word, 'ca') * 1_000_000))
            self.lexicon.add(word, count)
            loaded += 1

        seeded = 0
        for w in ESSENTIAL_WORDS:
            if not self.lexicon.contains(w):
                self.lexicon.add(w, 1000)
                seeded += 1

        print(f"[lexicon] {loaded:,} words (min_zipf={min_zipf}), "
              f"+{seeded} function words seeded")

    def load_catalog(self, songs: list[dict]) -> None:
        """
        Register songs. Each entry needs 'title' and 'artist'. Titles and
        artists are stored as whole phrases (the primary match unit) AND as
        tokens (for the fallback path).
        """
        t_added = a_added = 0
        for song in songs:
            raw_title  = (song.get('title')  or '').strip()
            raw_artist = (song.get('artist') or '').strip()
            title  = normalize(raw_title)
            artist = normalize(raw_artist)

            if title and title not in self.title_display:
                self.title_display[title] = raw_title
                self.title_phrase.add(title, FREQ_PHRASE)
                t_added += 1
            if artist and artist not in self.artist_display:
                self.artist_display[artist] = raw_artist
                self.artist_phrase.add(artist, FREQ_PHRASE)
                a_added += 1

            if artist and title:
                self.songs_by_artist.setdefault(artist, []).append(title)

            for tok in tokenize(title):
                if len(tok) >= 2 and not self.title_token.contains(tok):
                    self.title_token.add(tok, FREQ_TITLE_TOKEN)
            for tok in tokenize(artist):
                if len(tok) >= 2 and not self.artist_token.contains(tok):
                    self.artist_token.add(tok, FREQ_ARTIST_TOKEN)

        self._seg = None  # invalidate lazy segmentation index
        print(f"[catalog] {t_added} titles, {a_added} artists, "
              f"{len(self.title_token.entries())} title-tokens, "
              f"{len(self.artist_token.entries())} artist-tokens")

    # ------------------------------------------------------------------
    # Phrase strategies
    # ------------------------------------------------------------------

    def _phrase_match(self, text: str) -> list[Candidate]:
        """
        Fuzzy-match the whole query against artist / title phrases.
        Filter out low-confidence hits (e.g. a short 4-char title happens
        to be edit-distance 4 from a 7-char query) so they don't leak
        into suggestions.

        For single-word queries that are themselves common standalone
        words ("esta", "cel", "amor") only EXACT phrase matches are
        kept — we don't want fuzzy phrase matches turning a valid word
        into a different one ("esta" → "Estiu" at d=1).
        """
        ed = adaptive_max_ed(len(fold_accents(text)), cap=self.max_edit_distance)
        out: list[Candidate] = []
        out += self.artist_phrase.lookup(text, TIER_ARTIST_PHRASE, ed,
                                         tier_name='artist_phrase')
        out += self.title_phrase.lookup(text, TIER_TITLE_PHRASE, ed,
                                        tier_name='title_phrase')
        # Only EXACT matches when the query is a complete word or has a
        # clear accent-fix canonical. Stops "esta" → "Estiu" (d=1).
        if (self._is_common_standalone_word(text)
                or self._accent_canonical(text) is not None):
            out = [c for c in out if c.distance == 0]
        return [c for c in out if _is_confident_phrase(c)]

    def _is_common_standalone_word(self, text: str) -> bool:
        """
        True when `text` is a single valid word that the parser should
        leave alone — neither complete it ("cel" → "Celebraré") nor
        fuzzy-rewrite it ("cel" → "del"). Two ways to qualify:

        - Catalog-grounded: the word appears in some title and has
          non-trivial Catalan frequency (≥20).  Catches "cel", "amor",
          "dia", "boig" etc. that are real words used in titles.
        - High-frequency Catalan word (≥100). Catches "està", "mar",
          "sol", "ser" — words that aren't in any title but are clearly
          common standalone words the user is unlikely to be typing as
          a partial.

        Length must be at least 3 — 2-char inputs ("bo", "mo") are
        almost always partial typing and should still complete.
        Rare names ("lluis" freq=3, "sau" freq=2) don't qualify and so
        still complete to their artist phrases.
        """
        if ' ' in text or len(text) < 3:
            return False
        if self.title_token.contains(text) and self.lexicon.freq(text) >= 20:
            return True
        if self.lexicon.freq(text) >= 100:
            return True
        return False

    def _accent_canonical(self, text: str) -> str | None:
        """
        Return the canonical (significantly-more-frequent accented)
        lexicon variant of `text`, or None if there's no clear
        accent-fix opportunity. "esta" → "està" (1290 vs 70). When this
        fires, fuzzy phrase/completion candidates should be tightened to
        clean-prefix only — we don't want "esta" → "Estiu" (d=1) when
        the obvious fix is "esta" → "està" (just an accent).
        """
        if ' ' in text:
            return None
        folded = fold_accents(text)
        canonical = self.lexicon.fold_map.get(folded, text)
        if canonical == text:
            return None
        cf = self.lexicon.freq(canonical)
        tf = self.lexicon.freq(text)
        if cf >= 20 and cf >= max(3, tf * 3):
            return canonical
        return None

    def _completions(self, text: str) -> list[Candidate]:
        """
        Phrases whose accent-folded form starts with (or nearly starts with)
        the accent-folded query. Distance 0 means a clean prefix; non-zero
        means the user made typos in the prefix they typed so far.

        Skipped when the query is a single common standalone word ("cel",
        "amor", "dia"): a word is not "incomplete". A partial or rare form
        like "lluis" is still allowed to complete to "Lluís Llach".
        """
        q = fold_accents(text)
        if len(q) < 2:
            return []

        if self._is_common_standalone_word(text):
            return []

        # Adaptive prefix-edit budget. For 2-char queries this is 0 (only
        # exact prefixes), so "bo" can't fuzzy-complete to "joan manuel
        # serrat". Longer prefixes tolerate more.
        threshold = adaptive_max_ed(len(q), cap=self.max_edit_distance)
        # Accent fix in play → only clean prefixes ("lluis" still completes
        # to "Lluís Llach" because the prefix matches at d=0, but "esta"
        # won't fuzzy-complete to "Estiu").
        if self._accent_canonical(text) is not None:
            threshold = 0
        out: list[Candidate] = []

        def scan(index: _Index, tier: int, tier_name: str):
            for phrase in index.entries():
                pf = fold_accents(phrase)
                if len(pf) <= len(q):
                    continue
                pref = pf[:len(q)]
                d = 0 if pref == q else levenshtein(q, pref)
                if d <= threshold:
                    out.append(Candidate(phrase, d, tier, index.freq(phrase),
                                         tier_name=tier_name))

        scan(self.artist_phrase, TIER_COMPLETION_ARTIST, 'artist_completion')
        scan(self.title_phrase,  TIER_COMPLETION_TITLE,  'title_completion')
        return out

    def _split_match(self, text: str) -> list[Candidate]:
        """Split at each word boundary: (artist, title) and (title, artist)."""
        words = text.split()
        if len(words) < 2:
            return []

        out: list[Candidate] = []
        for i in range(1, len(words)):
            left  = ' '.join(words[:i])
            right = ' '.join(words[i:])
            led = adaptive_max_ed(len(fold_accents(left)),  cap=self.max_edit_distance)
            red = adaptive_max_ed(len(fold_accents(right)), cap=self.max_edit_distance)

            la = self.artist_phrase.lookup(left,  TIER_SPLIT_PHRASE, led,
                                           tier_name='split_phrase')
            rt = self.title_phrase.lookup(right, TIER_SPLIT_PHRASE, red,
                                          tier_name='split_phrase')
            for jc in _join(la, rt):
                out.append(jc)

            lt = self.title_phrase.lookup(left,  TIER_SPLIT_PHRASE, led,
                                          tier_name='split_phrase')
            ra = self.artist_phrase.lookup(right, TIER_SPLIT_PHRASE, red,
                                           tier_name='split_phrase')
            for jc in _join(lt, ra):
                out.append(jc)
        return out

    def _artist_expansions(self, text: str) -> list[Candidate]:
        """
        If the query matches an artist well, offer "artist + song" query
        completions. This is the "suggest completing queries" feature for
        the common case of "user typed an artist name, now suggest songs".

        Only fires when the underlying artist match is confident — weak
        fuzzy artist hits would otherwise spray unrelated songs into the
        suggestion list. Also skipped when the query is a single valid
        non-artist word: "cel" is a word and shouldn't get "Cesk Freixas
        Un dia qualsevol" as an expansion suggestion.
        """
        if text not in self.artist_display and self._is_common_standalone_word(text):
            return []

        ed = adaptive_max_ed(len(fold_accents(text)), cap=self.max_edit_distance)
        out: list[Candidate] = []
        for c in self.artist_phrase.lookup(text, TIER_ARTIST_PHRASE, ed,
                                           tier_name='artist_phrase'):
            if not _is_confident_phrase(c):
                continue
            for title in self.songs_by_artist.get(c.text, []):
                joined = f"{c.text} {title}"
                out.append(Candidate(joined, c.distance, TIER_EXPANSION,
                                     FREQ_PHRASE, tier_name='artist_expansion'))
        # Also expand on artist prefix matches (user typed partial artist).
        for c in self._completions_single(text, self.artist_phrase,
                                          TIER_COMPLETION_ARTIST,
                                          'artist_completion'):
            if not _is_confident_phrase(c):
                continue
            for title in self.songs_by_artist.get(c.text, []):
                joined = f"{c.text} {title}"
                out.append(Candidate(joined, c.distance, TIER_EXPANSION,
                                     FREQ_PHRASE, tier_name='artist_expansion'))
        return out

    def _completions_single(self, text: str, index: _Index, tier: int,
                            tier_name: str) -> list[Candidate]:
        q = fold_accents(text)
        if len(q) < 2:
            return []
        threshold = adaptive_max_ed(len(q), cap=self.max_edit_distance)
        out: list[Candidate] = []
        for phrase in index.entries():
            pf = fold_accents(phrase)
            if len(pf) <= len(q):
                continue
            pref = pf[:len(q)]
            d = 0 if pref == q else levenshtein(q, pref)
            if d <= threshold:
                out.append(Candidate(phrase, d, tier, index.freq(phrase),
                                     tier_name=tier_name))
        return out

    # ------------------------------------------------------------------
    # Token fallback
    # ------------------------------------------------------------------

    def _token_candidates(self, token: str) -> list[Candidate]:
        if len(token) < MIN_TOKEN_LEN_FOR_CORRECTION:
            return [Candidate(token, 0, TIER_LEXICON,
                              max(1, self.lexicon.freq(token)),
                              tier_name='lexicon')]

        # Exact hits via fold_map first. The fold_map resolves to the
        # *canonical* (most-frequent accented variant) form for each
        # index, so "esta" → "està", "cancons" → "cançons", "lluis" →
        # "Lluís" if the accented form exists. If the token is a valid
        # word in ANY index, we lock to those exact hits and don't offer
        # fuzzy alternatives — a valid word should not be "corrected"
        # just because a fuzzy neighbour sits in a higher-tier index
        # (otherwise "cel" gets rewritten to "del").
        folded = fold_accents(token)
        exact: list[Candidate] = []
        artist_canon = self.artist_token.fold_map.get(folded)
        title_canon  = self.title_token.fold_map.get(folded)
        lex_canon    = self.lexicon.fold_map.get(folded)
        if artist_canon:
            exact.append(Candidate(artist_canon, 0, TIER_ARTIST_TOKEN,
                                   FREQ_ARTIST_TOKEN, tier_name='artist_token'))
        if title_canon:
            exact.append(Candidate(title_canon, 0, TIER_TITLE_TOKEN,
                                   FREQ_TITLE_TOKEN, tier_name='title_token'))
        if lex_canon:
            exact.append(Candidate(lex_canon, 0, TIER_LEXICON,
                                   self.lexicon.freq(lex_canon),
                                   tier_name='lexicon'))
        if exact:
            return sorted(exact, key=lambda c: -c.score)

        # No exact hit anywhere — try fuzzy.
        ed = adaptive_max_ed(len(token), cap=MAX_ED_TOKEN)
        cands: list[Candidate] = []
        cands += self.artist_token.lookup(token, TIER_ARTIST_TOKEN, ed,
                                          tier_name='artist_token',
                                          verbosity=Verbosity.TOP)
        cands += self.title_token.lookup(token, TIER_TITLE_TOKEN, ed,
                                         tier_name='title_token',
                                         verbosity=Verbosity.TOP)
        cands += self.lexicon.lookup(token, TIER_LEXICON, ed,
                                     tier_name='lexicon',
                                     verbosity=Verbosity.TOP)

        best: dict[str, Candidate] = {}
        for c in cands:
            if c.text not in best or best[c.text].score < c.score:
                best[c.text] = c
        ranked = sorted(best.values(), key=lambda c: -c.score)

        if not ranked:
            return [Candidate(token, 0, TIER_LEXICON, 1, tier_name='lexicon')]

        top = ranked[0]
        if top.tier == TIER_LEXICON and top.distance > max(1, len(token) // 5):
            return [Candidate(token, 0, TIER_LEXICON, 1, tier_name='lexicon')]
        return ranked

    def _token_sequence_correction(self, tokens: list[str]) -> Candidate:
        """Correct each token independently and return the joined result."""
        out_tokens: list[str] = []
        total_dist = 0
        for tok in tokens:
            cands = self._token_candidates(tok)
            best = cands[0]
            out_tokens.append(best.text)
            total_dist += best.distance
        return Candidate(' '.join(out_tokens), total_dist, TIER_LEXICON, 1,
                         tier_name='lexicon')

    # ------------------------------------------------------------------
    # Word segmentation  (only for no-space blobs)
    # ------------------------------------------------------------------

    def _word_segment(self, text: str) -> str | None:
        if ' ' in text or len(text) < 6:
            return None

        # Don't segment if the blob itself is a valid word or has a close
        # single-word fuzzy correction. Users rarely drop spaces; they
        # much more often drop an accent or mistype a letter. Prefer
        # "enciclopedia" → "enciclopèdia" over "en cic lope dia".
        if (self.lexicon.contains(text)
                or self.title_token.contains(text)
                or self.artist_token.contains(text)):
            return None
        # Adaptive distance for "is there a close single-word fuzzy match?"
        # Clamped to MAX_ED_TOKEN (the build-time limit of these indexes).
        seg_ed = adaptive_max_ed(len(text), cap=MAX_ED_TOKEN)
        for idx in (self.lexicon, self.title_token, self.artist_token):
            if idx.lookup(text, 0, seg_ed, verbosity=Verbosity.TOP):
                return None

        if self._seg is None:
            seg = SymSpell(0, prefix_length=7)
            # Only seed segmentation with reasonably common lexicon words.
            # Including freq=1 entries leads to splits like "lib el lula"
            # because rare proper-noun fragments behave like "real" words.
            for w in self.lexicon.entries():
                f = self.lexicon.freq(w)
                if f >= MIN_SEGMENT_PART_FREQ:
                    seg.create_dictionary_entry(w, f)
            for w in self.title_token.entries():
                seg.create_dictionary_entry(w, FREQ_TITLE_TOKEN)
            for w in self.artist_token.entries():
                seg.create_dictionary_entry(w, FREQ_ARTIST_TOKEN)
            self._seg = seg
        r = self._seg.word_segmentation(text, max_edit_distance=0)
        if not r or not r.corrected_string:
            return None
        parts = r.corrected_string.split()
        if len(parts) < 2:
            return None
        for p in parts:
            in_catalog = (self.title_token.contains(p)
                          or self.artist_token.contains(p))
            in_lexicon = self.lexicon.freq(p) >= MIN_SEGMENT_PART_FREQ
            if not (in_catalog or in_lexicon or p in ESSENTIAL_WORDS):
                return None
            if len(p) <= 2 and p not in ESSENTIAL_WORDS:
                return None
        return r.corrected_string

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, query: str, top_k_suggestions: int = 4) -> dict:
        normalized = normalize(query)
        segmented  = self._word_segment(normalized) or normalized

        # Stage 2: phrase-level candidates (artist/title/split/completion/expand).
        phrase_cands: list[Candidate] = []
        phrase_cands += self._phrase_match(segmented)
        phrase_cands += self._completions(segmented)
        phrase_cands += self._split_match(segmented)
        phrase_cands += self._artist_expansions(segmented)

        # Is any phrase candidate confident enough to carry the result?
        q_len = len(fold_accents(segmented))
        threshold = max(1, q_len // 4)
        confident = any(
            c.distance <= threshold
            and c.tier >= TIER_COMPLETION_TITLE
            for c in phrase_cands
        )

        pool: list[Candidate] = list(phrase_cands)

        if not confident:
            # Stage 3: per-token lexicon correction as fallback.
            tokens = tokenize(segmented)
            if tokens:
                pool.append(self._token_sequence_correction(tokens))

        # Always keep a raw passthrough (de-prioritised) so catastrophic
        # failure modes fall back to showing the user what they typed.
        pool.append(Candidate(segmented, 0, TIER_LEXICON, 1,
                              tier_name='lexicon'))

        # Dedupe by normalised text, keep highest-scoring.
        best: dict[str, Candidate] = {}
        for c in pool:
            if c.text not in best or best[c.text].score < c.score:
                best[c.text] = c
        ranked = sorted(best.values(), key=lambda c: -c.score)

        top = ranked[0]
        # Prune suggestions: drop anything more than SUGGESTION_SCORE_GAP
        # below the winner — one tier-level buffer keeps us from listing
        # lexicon noise next to a phrase-tier winner.
        min_score = top.score - SUGGESTION_SCORE_GAP
        suggestions: list[str] = []
        seen = {top.text}
        for c in ranked[1:]:
            if c.text in seen:
                continue
            if c.score < min_score:
                break  # ranked is descending, rest are even lower
            if len(suggestions) >= top_k_suggestions:
                break
            # Skip de-prioritised passthroughs unless they are the only option.
            if c.tier == TIER_LEXICON and c.text == segmented:
                continue
            suggestions.append(_display(c.text, self.artist_display, self.title_display))
            seen.add(c.text)

        corrected_display = _display(top.text, self.artist_display, self.title_display)

        matched_artist, matched_title = self._detect_entities(top.text)

        # Word bag with per-word probability. Each candidate contributes
        # its tokens at weight = candidate_score / top_score; original
        # query tokens always carry a baseline weight (the user typed
        # them, so they're definitely part of what they meant). Filter
        # to words that meet the MIN_WORD_WEIGHT threshold.
        words = self._collect_words(query, ranked, top)

        return {
            'original':       query,
            'normalized':     normalized,
            'corrected':      corrected_display,
            'suggestions':    suggestions,
            'matched_artist': matched_artist,
            'matched_title':  matched_title,
            'words':          words,
            'tier':           top.tier_name or 'lexicon',
            'distance':       top.distance,
            'score':          round(top.score, 2),
            'confident':      confident,
        }

    def _collect_words(self, original: str, ranked: list[Candidate],
                       top: Candidate) -> dict[str, float]:
        """
        Build a {word: weight} dict where weight ∈ [0, 1] is the
        probability the user meant that word.

        Sources:
        - The original query tokens always get ORIGINAL_WORD_WEIGHT
          (they're literally what was typed).
        - Each pool candidate contributes its tokens at score/top_score.
          So tokens of the corrected phrase land near 1.0; tokens of a
          weaker suggestion land lower.
        - We take the max weight per word across sources.

        Words below MIN_WORD_WEIGHT are dropped — those came from
        marginal lexicon-tier candidates and would only add noise.

        Returned dict is ordered by descending weight.
        """
        weights: dict[str, float] = {}

        for w in tokenize(normalize(original)):
            if w:
                weights[w] = max(weights.get(w, 0.0), ORIGINAL_WORD_WEIGHT)

        top_score = top.score if top.score > 0 else 1.0
        for c in ranked:
            rel = c.score / top_score
            if rel < MIN_WORD_WEIGHT:
                break  # ranked is descending
            for w in tokenize(normalize(c.text)):
                if w and rel > weights.get(w, 0.0):
                    weights[w] = rel

        # Drop sub-threshold entries (could happen if an original token
        # only appeared at low weight and ORIGINAL_WORD_WEIGHT is below
        # the cutoff — keep this guard so the contract stays clean).
        weights = {w: round(v, 3) for w, v in weights.items()
                   if v >= MIN_WORD_WEIGHT}

        return dict(sorted(weights.items(), key=lambda kv: -kv[1]))

    def _detect_entities(self, text: str) -> tuple[str | None, str | None]:
        ma = self.artist_display.get(text)
        mt = self.title_display.get(text)
        if ma and mt:
            return ma, mt

        words = text.split()
        for i in range(len(words)):
            for j in range(i + 1, len(words) + 1):
                span = ' '.join(words[i:j])
                if ma is None and span in self.artist_display:
                    ma = self.artist_display[span]
                if mt is None and span in self.title_display:
                    mt = self.title_display[span]
        return ma, mt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _join(left: list[Candidate], right: list[Candidate]) -> list[Candidate]:
    """
    Combine the best left and right candidates into a joined split-match.
    Reject the pair when either half's distance is too large relative to
    the half's length — that's what prevents "boig" (4 chars) matching
    "zoo" (d=3) from producing "zoo X" garbage suggestions.
    """
    if not left or not right:
        return []
    lb = max(left,  key=lambda c: c.score)
    rb = max(right, key=lambda c: c.score)
    if not _is_confident_phrase(lb) or not _is_confident_phrase(rb):
        return []
    return [Candidate(
        f"{lb.text} {rb.text}",
        lb.distance + rb.distance,
        TIER_SPLIT_PHRASE,
        min(lb.freq, rb.freq),
        tier_name='split_phrase',
    )]


def _is_confident_phrase(cand: Candidate) -> bool:
    """
    A phrase candidate is "confident" when its edit distance is small
    relative to the length of the text it matched. One edit in a 3-4 char
    string is OK; more than that almost certainly means the two strings
    are different entities, not typos of each other.
    """
    n = len(fold_accents(cand.text))
    return cand.distance <= max(1, n // 3)


def _display(text: str,
             artist_display: dict[str, str],
             title_display: dict[str, str]) -> str:
    """
    Render a normalised candidate text back to display form by splitting
    it into artist/title spans where we can.
    """
    # Whole-phrase shortcut.
    if text in artist_display:
        return artist_display[text]
    if text in title_display:
        return title_display[text]

    # Try "artist title" (and "title artist") decompositions.
    words = text.split()
    for i in range(1, len(words)):
        left  = ' '.join(words[:i])
        right = ' '.join(words[i:])
        if left in artist_display and right in title_display:
            return f"{artist_display[left]} {title_display[right]}"
        if left in title_display and right in artist_display:
            return f"{title_display[left]} {artist_display[right]}"
        if left in artist_display and right not in title_display:
            # Artist prefix + free-form tail.
            return f"{artist_display[left]} {right}"
    return text


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    from catalog import SONGS

    parser = CatalanSongQueryParser()

    t0 = time.time()
    parser.load_lexicon(min_zipf=2.4)
    print(f"[init] lexicon ready in {time.time() - t0:.2f}s")

    t0 = time.time()
    parser.load_catalog(SONGS)
    print(f"[init] catalog ready in {time.time() - t0:.2f}s")

    test_queries = [
        # — phrase correction —
        "boig per tu",
        "bog per tu",
        "boigpertu",
        "boig per tyu",
        # — completion —
        "boig per",
        "lluis l",
        "sopa de",
        "manel jo vull",
        # — artist expansion —
        "lluis llach",
        "oques grasses",
        # — artist + title —
        "sau boig per tu",
        "sopa de cabra lempordà",
        "lluis lach lestaca",
        "marina rosel la gavna",
        "antonia font cami avall",
        "txarango respra",
        # — accent handling —
        "lluis llach",
        "antonia font",
        # — token fallback (lyrics-like) —
        "cancio d'amor",
        "catalunya amor mai",
        # — OOV / garbage —
        "mozart beethoven",
        "xyzqwe",
        # — completion of a song name mid-typing —
        "jo vull ser",
        "tots els noms",
    ]

    for q in test_queries:
        parser.parse(q)  # warm-up

    print()
    print(f"{'Query':<32} → {'Corrected':<40} {'Tier':<18} [ms]")
    print('-' * 105)
    total = 0.0
    for q in test_queries:
        t0 = time.perf_counter()
        r = parser.parse(q)
        dt = (time.perf_counter() - t0) * 1000
        total += dt
        print(f"{q:<32} → {r['corrected']:<40} {r['tier']:<18} {dt:6.2f}")
        if r['suggestions']:
            for s in r['suggestions'][:3]:
                print(f"{'':<34}  · {s}")
        if r['matched_artist'] or r['matched_title']:
            bits = []
            if r['matched_artist']:
                bits.append(f"artist={r['matched_artist']}")
            if r['matched_title']:
                bits.append(f"title={r['matched_title']}")
            print(f"{'':<34}  → {', '.join(bits)}")
        if r['words']:
            ws = ', '.join(f"{w}:{wt:.2f}" for w, wt in r['words'].items())
            print(f"{'':<34}  words: {ws}")
    print(f"\nAvg: {total / len(test_queries):.2f} ms per query "
          f"({len(SONGS)} songs in catalog)")

    print("\nInteractive mode — escriu una query (o 'q' per sortir):")
    while True:
        try:
            q = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ('q', 'quit', 'exit'):
            break
        if not q:
            continue
        t0 = time.perf_counter()
        r = parser.parse(q)
        dt = (time.perf_counter() - t0) * 1000
        print(f"  corrected : {r['corrected']}  [{r['tier']}, d={r['distance']}]")
        if r['suggestions']:
            print(f"  did you mean:")
            for s in r['suggestions']:
                print(f"    · {s}")
        if r['matched_artist']:
            print(f"  → artist: {r['matched_artist']}")
        if r['matched_title']:
            print(f"  → title : {r['matched_title']}")
        if r['words']:
            ws = ', '.join(f"{w}:{wt:.2f}" for w, wt in r['words'].items())
            print(f"  words     : {ws}")
        print(f"  ({dt:.2f} ms)")
