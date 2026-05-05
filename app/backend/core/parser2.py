"""
parser2.py — Catalan song-search query parser, v2 (clean rewrite).

Pipeline (each step adds candidates to the output bag):

    1. Lowercase + NFC normalisation.
    2. Phrase matching: walk every artist + title in the catalog, score
       by weighted edit distance, keep close ones.
    3. Per-word fuzzy: for every input word, find catalog-tokens and
       (optionally) lexicon entries within a custom edit-distance budget.

Edit distance is Damerau-Levenshtein with operation-specific costs:

    transposition (swap)     : 0.5    common typo, low penalty
    missing char (insert)    : 1.0    medium
    extra char (delete)      : 1.0    medium
    wrong char (substitute)  : 1.0 × keyboard_distance ∈ [0, 1]
                                       accent-only diff ≈ 0.15
                                       far keys → 1.0
    space (insert/delete)    : 2.0    rare mistake, expensive

Probability mapping:

    prob = exp(-edit_distance / DECAY_SCALE) × source_weight

source_weight: 1.0 for catalog matches, 0.7 for lexicon.

Output format
-------------
    {word: probability ∈ (0, 1]}, ordered by descending probability.
    Original input words are always present at probability 1.0.
    Words with prob < MIN_PROB are dropped.
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from collections import defaultdict
from functools import lru_cache


# ---------------------------------------------------------------------------
# Operation costs
# ---------------------------------------------------------------------------

COST_SWAP        = 0.5    # adjacent transposition
COST_INSERT      = 1.0    # source missing a char compared to target
COST_DELETE      = 1.0    # source has an extra char compared to target
COST_SUBSTITUTE  = 1.2    # base, multiplied by keyboard distance ∈ [0, 1].
                          # Higher than insert/delete because substitutions are
                          # active typing errors (pressed wrong key) rather than
                          # motor slips (missed a key). Set so 2 substitutions
                          # exceed MAX_WORD_DISTANCE — the model can't propose
                          # 'través' as a fix for 'grases' (3 cheap subs adding
                          # up to 1.5 was too forgiving).
COST_SPACE       = 2.0    # insert or delete a space
COST_DOT         = 0.10   # insert/delete the Catalan middle dot (l·l)

# Probability tuning. Distance is interpreted RELATIVE TO WORD LENGTH:
# a 1-char mistake in "es" (50% wrong) is much more suspicious than the
# same mistake in "enciclopedia" (~8% wrong), so the same absolute distance
# yields a far lower probability for short words.
RELATIVE_DECAY = 3.0  # prob = exp(-(distance / ref_len) * RELATIVE_DECAY)
MIN_PROB       = 0.50
TOP_K          = 20

# Lexicon candidates are also weighted by frequency: a high-freq word
# ("és" at freq 6610) is much more plausible than a rare one ("ez" at
# freq 1) at the same edit distance. FREQ_REF is the freq above which a
# word gets the full factor of 1.0 in the (single-arg) input-rarity check.
FREQ_REF = 500.0

# Softmax NULL-anchor score for the lexicon-candidate distribution. Sets
# the absolute scale: a single weak candidate scoring near 0 ends up with
# similar mass to the null (≈ 0.5), not full confidence. Higher values
# require candidates to be strictly better than null to beat it.
SOFTMAX_NULL_SCORE = 0.0

# Source multipliers on the prob
WEIGHT_CATALOG = 1.0
WEIGHT_LEXICON = 0.7    # generic lexicon hits sit just below catalog

# Threshold shaping. Common inputs raise the bar (corrections almost always
# noise); rare/OOV inputs lower it (almost certainly typos, surface the best
# matches). The cubic on COMMON_PENALTY leaves moderately-frequent words
# (ff~0.7) mostly alone and bites hard on top-tier ones (ff~1.0). RARE_RELAX
# is wide because the lexicon path softmaxes its candidates: a 0.22 prob in
# a 3-way distribution is meaningful, not noise. COMMON_PENALTY is wide
# enough that an already-common input ('carrer') won't get a one-edit
# catalog distractor ('carter') promoted to ~0.7 just because it happens
# to be in the catalog — the user typed a real Catalan word, trust them.
COMMON_PENALTY = 0.45
RARE_RELAX     = 0.30

# Distance caps so we never compute irrelevant matches.
MAX_PHRASE_DISTANCE = 4.0
MAX_WORD_DISTANCE   = 1.5


# ---------------------------------------------------------------------------
# QWERTY layout (with the Catalan ñ / ç keys folded onto their unaccented
# positions for keyboard-distance purposes)
# ---------------------------------------------------------------------------

_QWERTY = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
_KEY_POS: dict[str, tuple[int, int]] = {
    ch: (r, c) for r, row in enumerate(_QWERTY) for c, ch in enumerate(row)
}
_KEY_DIAG = math.hypot(len(_QWERTY[0]) - 1, len(_QWERTY) - 1)


@lru_cache(maxsize=4096)
def _fold_char(ch: str) -> str:
    """Strip diacritics; fold ç → c. Used so accent-only differences are cheap.

    Memoised: this is called millions of times per query inside the edit-
    distance hot loop, but the alphabet is small (≲ 200 chars), so an
    unbounded cache on first sight collapses to a dict lookup forever.
    """
    nf = unicodedata.normalize('NFKD', ch)
    base = ''.join(c for c in nf if not unicodedata.combining(c))
    if base in ('ç', 'Ç'):
        return 'c'
    return base.lower()


def _fold(text: str) -> str:
    return ''.join(_fold_char(c) for c in text)


# Piecewise keyboard-distance schedule. Raw Euclidean distance is rounded
# to the nearest int, then mapped through this table. Designed so:
# - same letter modulo accent  (treated separately): 0.10
# - adjacent keys (raw≈1):     0.60 — possible but not free
# - 2 keys apart (raw≈2):      0.80
# - 3 keys apart (raw≈3):      0.95
# - far away   (raw≥4):        1.00
# This stops "esta" from cheaply morphing into "fera" via three sub-1.0 hops.
_KBD_SCHEDULE = [0.0, 0.60, 0.80, 0.95, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
_ACCENT_ONLY_COST = 0.10


@lru_cache(maxsize=16384)
def keyboard_distance(a: str, b: str) -> float:
    """
    Substitution cost ∈ [0, 1] between two characters.

    - identical chars → 0
    - same letter modulo accent ("e" / "é" / "è") → 0.10  (very cheap)
    - adjacent QWERTY keys → 0.60  (typo, but a real edit)
    - far-apart keys / unknown chars → 1.0

    Memoised: called millions of times per query inside edit_distance, but
    only over the cartesian product of the small character alphabet — the
    cache stabilises within the first few queries.
    """
    if a == b:
        return 0.0
    fa, fb = _fold_char(a), _fold_char(b)
    if fa == fb:
        return _ACCENT_ONLY_COST
    pa, pb = _KEY_POS.get(fa), _KEY_POS.get(fb)
    if pa is None or pb is None:
        return 1.0
    raw = round(math.hypot(pa[1] - pb[1], pa[0] - pb[0]))
    return _KBD_SCHEDULE[min(raw, len(_KBD_SCHEDULE) - 1)]


# ---------------------------------------------------------------------------
# Custom edit distance
# ---------------------------------------------------------------------------

def edit_distance(a: str, b: str, cap: float = float('inf')) -> float:
    """
    Damerau-Levenshtein with weighted operations. `cap` provides an early
    exit: once every cell of a row exceeds `cap`, we return `cap + 1` so
    callers can cheaply skip hopeless candidates.
    """
    if a == b:
        return 0.0
    n, m = len(a) + 1, len(b) + 1
    dp = [[0.0] * m for _ in range(n)]
    for i in range(1, n):
        ca = a[i - 1]
        dp[i][0] = dp[i - 1][0] + (
            COST_SPACE if ca == ' ' else COST_DOT if ca == '·' else COST_DELETE
        )
    for j in range(1, m):
        cb = b[j - 1]
        dp[0][j] = dp[0][j - 1] + (
            COST_SPACE if cb == ' ' else COST_DOT if cb == '·' else COST_INSERT
        )

    for i in range(1, n):
        row_min = float('inf')
        for j in range(1, m):
            ca, cb = a[i - 1], b[j - 1]
            del_c = dp[i - 1][j] + (
                COST_SPACE if ca == ' ' else COST_DOT if ca == '·' else COST_DELETE
            )
            ins_c = dp[i][j - 1] + (
                COST_SPACE if cb == ' ' else COST_DOT if cb == '·' else COST_INSERT
            )
            sub_c = dp[i - 1][j - 1] + COST_SUBSTITUTE * keyboard_distance(ca, cb)
            best = min(del_c, ins_c, sub_c)
            if (i >= 2 and j >= 2
                    and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]):
                best = min(best, dp[i - 2][j - 2] + COST_SWAP)
            dp[i][j] = best
            if best < row_min:
                row_min = best
        if row_min > cap:
            return cap + 1.0
    return dp[n - 1][m - 1]


def distance_to_prob(d: float, ref_len: int) -> float:
    """
    Length-relative probability. The same absolute distance produces a
    much lower probability when matched against a short word — a 1-char
    mistake in "es" should not look as plausible as a 1-char mistake in
    "enciclopedia".
    """
    rel = d / max(ref_len, 2)
    return math.exp(-rel * RELATIVE_DECAY)


def freq_factor(freq: int) -> float:
    """
    Map a wordfreq raw frequency to a multiplier in (0, 1]. Common
    Catalan words get ≈1.0; rare ones (freq=1) get ≈0.10. log1p keeps
    the curve smooth across many orders of magnitude.
    """
    return min(1.0, math.log1p(max(0, freq)) / math.log1p(FREQ_REF))


# ---------------------------------------------------------------------------
# Normalisation & tokenisation
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zàèéíòóúïüçñ]+(?:·[a-zàèéíòóúïüçñ]+)*", re.IGNORECASE)
_CONTRACTION_RE = re.compile(r"([ldsmtn])'", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase, NFC, smart-quote → ASCII, l.l → l·l, collapse triple-letters."""
    text = unicodedata.normalize('NFC', text.lower().strip())
    text = (text.replace('’', "'")
                .replace('‘', "'")
                .replace('´', "'"))
    text = re.sub(r'(?<=[a-zà-ú])l[.\-]l(?=[a-zà-ú])', 'l·l', text)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)
    return text


def tokenize(text: str) -> list[str]:
    text = _CONTRACTION_RE.sub(r'\1 ', text)
    return [t for t in _TOKEN_RE.findall(text) if len(t) >= 2]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser2:
    """
    Bag-of-words query parser. `parse(query)` returns a dict mapping each
    candidate word to a probability ∈ (0, 1] that the user meant that word.
    """

    def __init__(self):
        # Phrase entries: (normalized, display).
        # Title and artist phrases are kept in separate lists so we can
        # weight or report them differently if needed.
        self.titles: list[tuple[str, str]] = []
        self.artists: list[tuple[str, str]] = []

        # Catalog tokens — every word that appears in any title or artist.
        self.catalog_tokens: set[str] = set()

        # Length-bucket indexes so phrase / token fuzzy matching only scans
        # candidates whose length is within the relevant edit-distance
        # budget — turns a per-query O(N) scan into O(N / buckets).
        self._titles_by_len:  dict[int, list[tuple[str, str]]] = defaultdict(list)
        self._artists_by_len: dict[int, list[tuple[str, str]]] = defaultdict(list)
        self._cat_tokens_by_len: dict[int, list[str]] = defaultdict(list)

        # 2-gram inverted index over accent-folded catalog tokens — same
        # role as `_lex_2gram` below, but for the (potentially 100k+) set
        # of words that appear in titles and artists. Without this, a query
        # like "sau" would force a per-token edit-distance call across the
        # entire token set; with it, we only score candidates that share at
        # least one bigram (or its swap-corrected mirror) with the input.
        self._cat_2gram: dict[str, set[str]] = defaultdict(set)

        # Generic Catalan lexicon (optional).
        self.lexicon: dict[str, int] = {}

        # 2-gram inverted index over the lexicon's accent-folded forms,
        # used to filter fuzzy-match candidates without scanning all 50k+
        # entries per input word.
        self._lex_2gram: dict[str, set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_catalog(self, songs: list[dict]) -> None:
        seen_titles, seen_artists = set(), set()
        for s in songs:
            t_disp = (s.get('title') or '').strip()
            a_disp = (s.get('artist') or '').strip()
            t = normalize(t_disp)
            a = normalize(a_disp)
            if t and t not in seen_titles:
                entry = (t, t_disp)
                self.titles.append(entry)
                self._titles_by_len[len(t)].append(entry)
                seen_titles.add(t)
                self.catalog_tokens.update(tokenize(t))
            if a and a not in seen_artists:
                entry = (a, a_disp)
                self.artists.append(entry)
                self._artists_by_len[len(a)].append(entry)
                seen_artists.add(a)
                self.catalog_tokens.update(tokenize(a))

        # Length buckets + accent-folded 2-gram index over catalog tokens.
        # Built once so per-query word fuzzy is a posting-list lookup, not
        # a full scan.
        for tok in self.catalog_tokens:
            self._cat_tokens_by_len[len(tok)].append(tok)
            folded = _fold(tok)
            for i in range(len(folded) - 1):
                self._cat_2gram[folded[i:i + 2]].add(tok)
        print(f"[catalog] {len(self.titles)} titles, {len(self.artists)} "
              f"artists, {len(self.catalog_tokens)} unique tokens")

    def load_lexicon(self, min_zipf: float = 2.4, top_n: int = 100_000) -> None:
        try:
            from wordfreq import top_n_list, zipf_frequency, word_frequency
        except ImportError as e:
            raise RuntimeError("wordfreq is required for the lexicon") from e
        for w in top_n_list('ca', top_n):
            if zipf_frequency(w, 'ca') < min_zipf:
                continue
            w = w.strip().lower()
            if len(w) < 2 or not re.search(r'[a-zàèéíòóúïüç]', w):
                continue
            freq = max(1, int(word_frequency(w, 'ca') * 1_000_000))
            self.lexicon[w] = freq
            folded = _fold(w)
            for i in range(len(folded) - 1):
                self._lex_2gram[folded[i:i + 2]].add(w)
        print(f"[lexicon] {len(self.lexicon):,} words")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(
        self,
        query: str,
        top_k: int = TOP_K,
        phrase_match: bool = True,
    ) -> dict[str, float]:
        """
        ``phrase_match`` toggles the full-query-against-catalog-phrase scan.
        Disable it when an external retrieval layer (e.g. an inverted index)
        already handles multi-word matching: phrase scanning is O(catalog)
        in worst case and dominates latency for large catalogs, while word-
        level fuzzy + the inverted index together cover the same recall for
        per-word typos.
        """
        q = normalize(query)
        words = tokenize(q)

        result: dict[str, float] = {}

        # Step 1: input words always at prob 1.0 — they're literally what
        # the user typed.
        for w in words:
            result[w] = 1.0

        # Step 2: phrase match against full title/artist phrases.
        if phrase_match:
            self._phrase_match(q, result)

        # Step 3: per-word fuzzy expansion + glued-word split.
        for w in words:
            self._word_fuzzy(w, result)
            self._split_match(w, result)

        # Per-step filters already enforce a min-prob (MIN_PROB shifted by
        # COMMON_PENALTY/RARE_RELAX), so the global cut here is just a
        # safety floor below which nothing should ever appear.
        floor = MIN_PROB - RARE_RELAX
        ranked = sorted(result.items(), key=lambda kv: -kv[1])
        return {w: round(p, 3) for w, p in ranked[:top_k] if p >= floor}

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _phrase_match(self, query: str, result: dict[str, float]) -> None:
        ql = len(query)
        # Length-bucketed scan: only iterate phrases whose length is
        # within MAX_PHRASE_DISTANCE of the query. With a 60k-phrase
        # catalog this turns a per-query 60k-iteration scan into a
        # few-thousand-iteration one (one bucket per length).
        max_d = int(MAX_PHRASE_DISTANCE)
        for length in range(max(0, ql - max_d), ql + max_d + 1):
            bucket = self._titles_by_len.get(length)
            if bucket:
                self._phrase_scan(query, ql, bucket, result)
            bucket = self._artists_by_len.get(length)
            if bucket:
                self._phrase_scan(query, ql, bucket, result)

    @staticmethod
    def _phrase_scan(query: str, ql: int, bucket, result: dict[str, float]) -> None:
        for phrase, _ in bucket:
            d = edit_distance(query, phrase, cap=MAX_PHRASE_DISTANCE)
            if d > MAX_PHRASE_DISTANCE:
                continue
            p = distance_to_prob(d, max(ql, len(phrase))) * WEIGHT_CATALOG
            if p < MIN_PROB:
                continue
            for tok in tokenize(phrase):
                if p > result.get(tok, 0.0):
                    result[tok] = p

    def _word_fuzzy(self, word: str, result: dict[str, float]) -> None:
        wlen = len(word)
        # Length budget is tight (1) because each insert/delete already
        # costs 1.0 — but middle dots are cheap (COST_DOT), so a candidate
        # with a `·` the input lacks (or vice versa) is allowed extra slack.
        input_dots = word.count('·')

        input_freq = self.lexicon.get(word, 0)
        input_ff = freq_factor(input_freq)
        rarity = 1 - input_ff
        # Threshold blends two effects. Common inputs (rarity≈0) raise the
        # bar so we don't propose noise corrections; rare/OOV inputs lower
        # it so the best near-matches surface.
        min_prob_word = (MIN_PROB
                         + COMMON_PENALTY * input_ff ** 3
                         - RARE_RELAX * rarity)
        # OOV input → trust the lexicon at full weight; common input keeps
        # the standard 0.7 lexicon penalty so catalog hits stay preferred.
        lex_weight = WEIGHT_LEXICON + (1 - WEIGHT_LEXICON) * rarity

        # Catalog tokens — narrow with length buckets + 2-gram filter so we
        # don't compute edit_distance against every catalog word. For an
        # input of length 4 we only consider buckets [3, 4, 5] (insertion/
        # deletion costs are 1.0, MAX_WORD_DISTANCE = 1.5), and within
        # those, only tokens that share an accent-folded bigram (or its
        # swap-corrected mirror) with the input.
        folded_in = _fold(word)
        cat_candidates: set[str] = set()
        for i in range(len(folded_in) - 1):
            cat_candidates.update(self._cat_2gram.get(folded_in[i:i + 2], ()))
            tr = folded_in[i + 1] + folded_in[i]
            cat_candidates.update(self._cat_2gram.get(tr, ()))
        # Also pull in same-length tokens with no shared bigram (e.g. the
        # input is a single bigram or has unusual characters), via the
        # length bucket. Keeps recall on very short inputs.
        for length in range(max(1, wlen - 1), wlen + 2):
            bucket = self._cat_tokens_by_len.get(length)
            if bucket and len(bucket) <= 256:
                cat_candidates.update(bucket)

        for tok in cat_candidates:
            if abs(len(tok) - wlen) > 1 + input_dots + tok.count('·'):
                continue
            d = edit_distance(word, tok, cap=MAX_WORD_DISTANCE)
            if d > MAX_WORD_DISTANCE:
                continue
            p = distance_to_prob(d, max(wlen, len(tok))) * WEIGHT_CATALOG
            if p < min_prob_word:
                continue
            if p > result.get(tok, 0.0):
                result[tok] = p

        # Lexicon — pre-filter via 2-gram overlap so we don't scan 50k
        # words per input token. Also include reversed bigrams so a swap
        # typo at the start of the word ("amro" → "amor") still surfaces
        # candidates whose first bigram is "am" (the swap-corrected form).
        if not self.lexicon:
            return
        folded = _fold(word)
        candidates: set[str] = set()
        for i in range(len(folded) - 1):
            candidates.update(self._lex_2gram.get(folded[i:i + 2], ()))
            tr = folded[i + 1] + folded[i]
            candidates.update(self._lex_2gram.get(tr, ()))

        # Score every viable candidate, then softmax the lot against a NULL
        # anchor to convert raw scores into a distribution. Softmax does the
        # work that hand-tuned freq factors used to: it concentrates mass on
        # the strongest candidate(s), shares mass evenly when many candidates
        # are similar, and squashes the long tail of freq-1 noise (proper
        # nouns, foreign loanwords) — all without an absolute frequency
        # floor that arbitrarily cuts moderately-rare real Catalan words.
        # The NULL anchor (score 0) sets the absolute scale: when the best
        # candidate is weak, no candidate gets near full confidence.
        #
        # Accent-fixes are handled out-of-band: when the candidate's folded
        # form matches the input's, the score formula's freq prior would let
        # a higher-freq but more distant word win (e.g., 'estar' over 'està'
        # for input 'esta'), but accent-only edits are reliable enough that
        # they should be promoted directly via distance-to-prob. Only fire
        # in the typo→fix direction (cand at least as common as input) to
        # avoid promoting Spanish 'está' over correct Catalan 'està'.
        folded_word = folded
        scored: list[tuple[str, float]] = []
        for cand in candidates:
            if abs(len(cand) - wlen) > 1 + input_dots + cand.count('·'):
                continue
            d = edit_distance(word, cand, cap=MAX_WORD_DISTANCE)
            if d > MAX_WORD_DISTANCE:
                continue
            if _fold(cand) == folded_word and self.lexicon[cand] >= input_freq:
                p = distance_to_prob(d, max(wlen, len(cand))) * lex_weight
                if p < min_prob_word:
                    continue
                if p > result.get(cand, 0.0):
                    result[cand] = p
                continue
            L = max(wlen, len(cand))
            score = -d / L * RELATIVE_DECAY + math.log1p(self.lexicon[cand])
            scored.append((cand, score))

        if not scored:
            return

        max_score = max(SOFTMAX_NULL_SCORE, max(s for _, s in scored))
        sum_exps = math.exp(SOFTMAX_NULL_SCORE - max_score) + sum(
            math.exp(s - max_score) for _, s in scored
        )
        for cand, score in scored:
            p = math.exp(score - max_score) / sum_exps * lex_weight
            if p < min_prob_word:
                continue
            if p > result.get(cand, 0.0):
                result[cand] = p

    def _split_match(self, word: str, result: dict[str, float]) -> None:
        """
        Try interpreting a long token as two glued-together words. Only
        fires when both halves are real words, the rarer half clears an
        absolute frequency floor (so 'lel' freq=1 doesn't qualify), AND
        each half is more frequent than the whole — so common words like
        'esta' aren't split into 'es'+'ta' (where 'ta' is rarer than
        'esta'), but OOV concatenations like 'expressióculturals' or
        'pertu' are. Catalog tokens count as effectively-infinite
        frequency: they're in the user's data, so they trump any lexicon
        whole and bypass the freq floor.
        """
        if word in self.catalog_tokens:
            return
        whole_freq = self.lexicon.get(word, 0)

        BIG = 10 ** 9
        MIN_HALF_FREQ = 20  # ≈ zipf 4.3, filters lexicon junk like 'lel' (freq 1)

        def _freq(w: str) -> int:
            f = self.lexicon.get(w, 0)
            if w in self.catalog_tokens:
                f += BIG
            return f

        best: tuple[int, str, str] | None = None  # (min-half-freq, left, right)
        for i in range(2, len(word) - 1):
            left, right = word[:i], word[i:]
            lf, rf = _freq(left), _freq(right)
            if min(lf, rf) <= max(whole_freq, MIN_HALF_FREQ):
                continue
            score = min(lf, rf)
            if best is None or score > best[0]:
                best = (score, left, right)

        if best is None:
            return
        _, left, right = best

        rarity = 1 - freq_factor(whole_freq)
        lex_weight = WEIGHT_LEXICON + (1 - WEIGHT_LEXICON) * rarity
        # Treat the missing space as a single-char edit (one of the most
        # common typos), not the harsh COST_SPACE used in phrase matching:
        # the lexicon checks above already prove the boundary is real.
        base = distance_to_prob(1.0, len(word))
        for half in (left, right):
            weight = WEIGHT_CATALOG if half in self.catalog_tokens else lex_weight
            p = base * weight
            if p > result.get(half, 0.0):
                result[half] = p


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    from catalog import SONGS

    parser = Parser2()

    t0 = time.time()
    parser.load_catalog(SONGS)
    print(f"[init] catalog ready in {time.time() - t0:.2f}s")

    t0 = time.time()
    parser.load_lexicon(min_zipf=2.4)
    print(f"[init] lexicon ready in {time.time() - t0:.2f}s")

    test_queries = [
        # short / partial typing
        "bo", "mo", "lluis l", "boig per", "sopa de",
        # phrase match (clean)
        "boig per tu", "lluis llach",
        # phrase match (typos)
        "bog per tu", "lluis lach lestaca", "antonia font cami avall",
        # accent-only fixes
        "esta", "està", "cancio", "cançó", "amor", "lluis",
        # words that should stay (real words)
        "cel", "dia", "nit", "amor", "festa",
        # segmentation cases (should be expensive, mostly stay)
        "boigpertu", "enciclopedia", "libelula",
        # OOV / garbage
        "mozart beethoven", "xyzqwe",
    ]

    print()
    print(f"{'Query':<32} {'Words (prob)':<70} [ms]")
    print('-' * 110)
    total = 0.0
    for q in test_queries:
        # warm-up + time
        parser.parse(q)
        t0 = time.perf_counter()
        r = parser.parse(q)
        dt = (time.perf_counter() - t0) * 1000
        total += dt
        top = list(r.items())[:8]
        rendering = ', '.join(f"{w}:{p:.2f}" for w, p in top)
        if len(r) > 8:
            rendering += f", … ({len(r) - 8} more)"
        print(f"{q:<32} {rendering:<70} {dt:6.1f}")
    print(f"\nAvg: {total / len(test_queries):.1f} ms per query")

    print("\nInteractive mode — type a query (or 'q' to quit):")
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
        print(f"  {len(r)} words ({dt:.1f} ms):")
        for w, p in r.items():
            print(f"    {p:.2f}  {w}")