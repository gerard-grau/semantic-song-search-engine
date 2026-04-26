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


# ---------------------------------------------------------------------------
# Operation costs
# ---------------------------------------------------------------------------

COST_SWAP        = 0.5    # adjacent transposition
COST_INSERT      = 1.0    # source missing a char compared to target
COST_DELETE      = 1.0    # source has an extra char compared to target
COST_SUBSTITUTE  = 1.0    # base, multiplied by keyboard distance ∈ [0, 1]
COST_SPACE       = 2.0    # insert or delete a space

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
# word gets the full factor of 1.0.
FREQ_REF = 500.0

# Source multipliers on the prob
WEIGHT_CATALOG = 1.0
WEIGHT_LEXICON = 0.7    # generic lexicon hits sit just below catalog

# Threshold shaping. Common inputs raise the bar (corrections almost always
# noise); rare/OOV inputs lower it (almost certainly typos, surface the best
# matches). The cubic on COMMON_PENALTY leaves moderately-frequent words
# (ff~0.7) mostly alone and bites hard on top-tier ones (ff~1.0).
COMMON_PENALTY = 0.30
RARE_RELAX     = 0.15

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


def _fold_char(ch: str) -> str:
    """Strip diacritics; fold ç → c. Used so accent-only differences are cheap."""
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


def keyboard_distance(a: str, b: str) -> float:
    """
    Substitution cost ∈ [0, 1] between two characters.

    - identical chars → 0
    - same letter modulo accent ("e" / "é" / "è") → 0.10  (very cheap)
    - adjacent QWERTY keys → 0.60  (typo, but a real edit)
    - far-apart keys / unknown chars → 1.0
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
        dp[i][0] = dp[i - 1][0] + (COST_SPACE if a[i - 1] == ' ' else COST_DELETE)
    for j in range(1, m):
        dp[0][j] = dp[0][j - 1] + (COST_SPACE if b[j - 1] == ' ' else COST_INSERT)

    for i in range(1, n):
        row_min = float('inf')
        for j in range(1, m):
            ca, cb = a[i - 1], b[j - 1]
            del_c = dp[i - 1][j] + (COST_SPACE if ca == ' ' else COST_DELETE)
            ins_c = dp[i][j - 1] + (COST_SPACE if cb == ' ' else COST_INSERT)
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

_TOKEN_RE = re.compile(r"[a-zàèéíòóúïüç]+(?:·[a-zàèéíòóúïüç]+)*", re.IGNORECASE)
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
                self.titles.append((t, t_disp))
                seen_titles.add(t)
                self.catalog_tokens.update(tokenize(t))
            if a and a not in seen_artists:
                self.artists.append((a, a_disp))
                seen_artists.add(a)
                self.catalog_tokens.update(tokenize(a))
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

    def parse(self, query: str, top_k: int = TOP_K) -> dict[str, float]:
        q = normalize(query)
        words = tokenize(q)

        result: dict[str, float] = {}

        # Step 1: input words always at prob 1.0 — they're literally what
        # the user typed.
        for w in words:
            result[w] = 1.0

        # Step 2: phrase match against full title/artist phrases.
        self._phrase_match(q, result)

        # Step 3: per-word fuzzy expansion.
        for w in words:
            self._word_fuzzy(w, result)

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
        for phrase, _ in self.titles + self.artists:
            # Length filter — DL distance is at least |len(a) - len(b)|
            # under unit costs; with our space cost being 2, the lower
            # bound is even higher when one side has more spaces. Cheap
            # gate.
            if abs(len(phrase) - ql) > MAX_PHRASE_DISTANCE:
                continue
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
        # Length filter is much tighter than the distance cap because each
        # insert/delete already costs 1.0; a candidate >1 char shorter or
        # longer than the input can't fit under the cap unless it's stuffed
        # with cheap accent-only diffs, which the fold-cheap substitution
        # already captures.
        len_window = 1

        input_freq = self.lexicon.get(word, 0)
        input_ff = freq_factor(input_freq)
        rarity = 1 - input_ff
        # Threshold blends two effects. Common inputs (rarity≈0) raise the
        # bar so we don't propose noise corrections; rare/OOV inputs lower
        # it so the best near-matches surface. Candidates are still weighted
        # by their own frequency, so rare candidates get filtered out even
        # when the input is OOV — only common Catalan words win.
        min_prob_word = (MIN_PROB
                         + COMMON_PENALTY * input_ff ** 3
                         - RARE_RELAX * rarity)
        # OOV input → trust the lexicon at full weight; common input keeps
        # the standard 0.7 lexicon penalty so catalog hits stay preferred.
        lex_weight = WEIGHT_LEXICON + (1 - WEIGHT_LEXICON) * rarity

        # Catalog tokens — small set, brute force.
        for tok in self.catalog_tokens:
            if abs(len(tok) - wlen) > len_window:
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

        folded_word = folded
        for cand in candidates:
            if abs(len(cand) - wlen) > len_window:
                continue
            d = edit_distance(word, cand, cap=MAX_WORD_DISTANCE)
            if d > MAX_WORD_DISTANCE:
                continue
            # Accent-fix bypass: when the unaccented forms match, skip the
            # freq penalty so a rare accented form ("enciclopèdia") still
            # wins against an unaccented typo ("enciclopedia"). Only apply
            # it in the typo→fix direction — i.e. cand is at least as
            # common as the input. Otherwise we'd promote rare junk like
            # Spanish "está" when the user already typed proper "està".
            if _fold(cand) == folded_word and self.lexicon[cand] >= input_freq:
                ff = 1.0
            else:
                ff = freq_factor(self.lexicon[cand])
            p = distance_to_prob(d, max(wlen, len(cand))) * lex_weight * ff
            if p < min_prob_word:
                continue
            if p > result.get(cand, 0.0):
                result[cand] = p


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
