"""
parser2.py — Catalan query parser, v3 (probabilistic spell-checker).

Given an input word the parser returns a probability distribution over
what the user *might have meant*:

  * the input word itself (assumed-OOV inputs get a tiny prior),
  * lexicon entries within a small edit-distance budget,
  * pairs of two real words that could explain the input as a missing
    space (e.g. "moltbe" → "molt be").

For multi-word queries each word is parsed independently and the per-
word distributions are merged with `max` per duplicate candidate.

Single-candidate probability
----------------------------

    p_raw = exp(-DECAY * d / L) * freq_factor(freq)

where d is a custom Damerau-Levenshtein distance, L is the *input
word's length* (clamped to ≥ 2), and freq_factor maps a wordfreq raw
frequency to a multiplier in (0, 1]. Using the input length means two
candidates that are both "one edit away" get the same exp factor
regardless of their own length — so e.g. "bo" and "blog" each cost
the same single insert/delete from "bog", and freq picks the winner.

Operation costs that go into d:

    transposition (swap of 2 adjacent chars)         COST_SWAP     (0.5)
    insert / delete  (regular char)                  COST_INSERT/DELETE (1.0)
    substitution: keys ARE adjacent on QWERTY        COST_SUB_ADJ  (0.85)
    substitution: keys are NOT adjacent              COST_SUB_FAR  (1.5)
    accent / fold-equivalent                         COST_ACCENT   (0.1)
        same letter modulo accent  (e ↔ é)
        ç ↔ c
        l ↔ ç-cedilla, etc.
        insert/delete of the Catalan middle dot (·)

The input word itself
---------------------

The input gets d = 0 (so the exp factor is exactly 1), but the
freq_factor still applies. Words not in the lexicon are assigned a
synthetic frequency equal to half of the lexicon's minimum (so by
construction lower than any known word) — this gives OOV inputs
a small but positive prior instead of a zero.

Pair-of-words candidates
------------------------

For every binary split of the input word into two halves that are
both real lexicon words we compute each half's probability with
d = SPLIT_COST = 1.5 (the implicit "missing space" edit) and combine
them via the *geometric mean* — sqrt(p_left · p_right). Both halves
need to be plausible for the pair to score, but a strong half partly
makes up for a weaker one. The pair is reported as a single key
"left right" (with the recovered space).

Author boost
------------

To favour corrections that land on the artists of popular Catalan
songs over corrections that land on incidental common-word neighbours,
any candidate whose word matches a token derived from the hardcoded
``_TOP_1000_AUTHORS`` list (extracted from the top-1000 entries of
``top_5000_songs.csv``) has its freq factor treated as if its raw
frequency were FREQ_REF — saturating freq_factor to 1.0. The boost
applies to the input word itself, to fuzzy-lexicon candidates, and to
each half of a pair-of-words split. Stopwords that happen to appear
in artist names ("el", "la", "de"…) already have freq_factor ≈ 1.0
from their natural frequency, so the boost is a no-op for them; it
only meaningfully lifts rare names like "llach" or "txarango".

Normalisation
-------------

Raw probabilities don't sum to 1 across candidates, so per input word
we apply a softmax with temperature T:

    p_norm[c] = exp(p_raw[c] / T) / Σ exp(p_raw[i] / T)

Lower T sharpens the distribution (the strongest candidate keeps
disproportionately more mass); higher T flattens it. T = 0.10 was
tuned so a correctly-typed common Catalan word ('amor', 'casa',
'feliç', 'cançó'…) ends up at ≥ 90% of the per-word probability
mass, while typo inputs still surface a useful spread of correction
alternatives instead of collapsing to one candidate.

Tuning the decay
----------------

A real-word input naturally dominates its distribution (its raw value
is freq_factor(common-freq) ≈ 1, while its alternates lose factors of
exp(-DECAY · d/L)). For OOV inputs it competes against close fuzzy
matches and can shrink. If the input word's normalised probability
needs to stay higher, raise DECAY: it crushes alternates faster (they
have d > 0) while leaving the input untouched (its d = 0).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache

import config


# ---------------------------------------------------------------------------
# Tunable constants — sourced from config.py (see that file for rationale).
# Names preserved here so existing imports like
# ``from app.backend.core.parser2 import MAX_WORD_DISTANCE`` keep working.
# ---------------------------------------------------------------------------

COST_SWAP        = config.PARSER_COST_SWAP
COST_INSERT      = config.PARSER_COST_INSERT
COST_DELETE      = config.PARSER_COST_DELETE
COST_SUB_ADJ     = config.PARSER_COST_SUB_ADJ
COST_SUB_FAR     = config.PARSER_COST_SUB_FAR
COST_ACCENT      = config.PARSER_COST_ACCENT
COST_SPACE       = config.PARSER_COST_SPACE

DECAY            = config.PARSER_DECAY
SPLIT_COST       = config.PARSER_SPLIT_COST
SOFTMAX_T        = config.PARSER_SOFTMAX_T

KEEP_TOP_N       = config.PARSER_KEEP_TOP_N
PROB_FLOOR       = config.PARSER_PROB_FLOOR
INPUT_RAW_FLOOR  = config.PARSER_INPUT_RAW_FLOOR
FREQ_REF         = config.PARSER_FREQ_REF

MAX_WORD_DISTANCE   = config.PARSER_MAX_WORD_DISTANCE
MAX_PHRASE_DISTANCE = config.PARSER_MAX_PHRASE_DISTANCE


# ---------------------------------------------------------------------------
# QWERTY layout (Catalan ñ / ç fold to their unaccented positions)
# ---------------------------------------------------------------------------

_QWERTY = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
_KEY_POS: dict[str, tuple[int, int]] = {
    ch: (r, c) for r, row in enumerate(_QWERTY) for c, ch in enumerate(row)
}


@lru_cache(maxsize=4096)
def _fold_char(ch: str) -> str:
    """Strip diacritics; fold ç → c. Used wherever 'same letter modulo
    accent' should look identical (substitution cost, accent-only fix)."""
    nf = unicodedata.normalize('NFKD', ch)
    base = ''.join(c for c in nf if not unicodedata.combining(c))
    if base in ('ç', 'Ç'):
        return 'c'
    return base.lower()


def _fold(text: str) -> str:
    return ''.join(_fold_char(c) for c in text)


def _qwerty_adjacent(fa: str, fb: str) -> bool:
    """True if two folded characters sit on horizontally adjacent QWERTY
    keys — same row, one column apart. Vertical neighbours (g/t, g/b) and
    diagonals (g/n, g/y) do NOT count — typo slips most often move the
    finger left or right along the home row, not up or down to a different
    row. Unknown characters never count as adjacent."""
    pa, pb = _KEY_POS.get(fa), _KEY_POS.get(fb)
    if pa is None or pb is None:
        return False
    return pa[0] == pb[0] and abs(pa[1] - pb[1]) == 1


@lru_cache(maxsize=16384)
def substitution_cost(a: str, b: str) -> float:
    """
    Replacement cost of character `a` with character `b`:

        identical                       → 0.0
        same letter modulo accent /     → COST_ACCENT  (0.1)
            ç ↔ c
        adjacent QWERTY keys            → COST_SUB_ADJ (0.85)
        anything else                   → COST_SUB_FAR (1.5)
    """
    if a == b:
        return 0.0
    fa, fb = _fold_char(a), _fold_char(b)
    if fa == fb:
        return COST_ACCENT
    return COST_SUB_ADJ if _qwerty_adjacent(fa, fb) else COST_SUB_FAR


# ---------------------------------------------------------------------------
# Edit distance (weighted Damerau-Levenshtein)
# ---------------------------------------------------------------------------

def edit_distance(a: str, b: str, cap: float = float('inf')) -> float:
    """Operation-weighted DL distance from `a` to `b`. `cap` provides an
    early exit: as soon as every cell of a row exceeds `cap`, we return
    `cap + 1` so callers can cheaply skip hopeless candidates.

    Insert/delete of the Catalan middle dot `·` is charged COST_ACCENT
    (it's effectively an accent on l / ll), not COST_INSERT."""
    if a == b:
        return 0.0
    n, m = len(a) + 1, len(b) + 1
    dp = [[0.0] * m for _ in range(n)]

    def _ins_del_cost(ch: str, base: float) -> float:
        if ch == ' ':   return COST_SPACE
        if ch == '·':   return COST_ACCENT
        return base

    for i in range(1, n):
        dp[i][0] = dp[i - 1][0] + _ins_del_cost(a[i - 1], COST_DELETE)
    for j in range(1, m):
        dp[0][j] = dp[0][j - 1] + _ins_del_cost(b[j - 1], COST_INSERT)

    for i in range(1, n):
        row_min = float('inf')
        for j in range(1, m):
            ca, cb = a[i - 1], b[j - 1]
            del_c = dp[i - 1][j] + _ins_del_cost(ca, COST_DELETE)
            ins_c = dp[i][j - 1] + _ins_del_cost(cb, COST_INSERT)
            sub_c = dp[i - 1][j - 1] + substitution_cost(ca, cb)
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


# ---------------------------------------------------------------------------
# Probability helpers
# ---------------------------------------------------------------------------

def freq_factor(freq: float) -> float:
    """Map a wordfreq raw frequency to a multiplier in (0, 1]. log1p
    curve saturates at 1.0 around freq = FREQ_REF (500). freq=1 noise
    gets ~0.11; the OOV prior of 0.5 gets ~0.07."""
    return min(1.0, math.log1p(max(0.0, freq)) / math.log1p(FREQ_REF))


def distance_to_prob(d: float, ref_len: int) -> float:
    """The exp-decay factor: exp(-DECAY * d / max(L, 2)). Length-relative
    so a 1-char miss in a short word penalises more than the same miss
    in a long word."""
    return math.exp(-DECAY * d / max(ref_len, 2))


# ---------------------------------------------------------------------------
# Normalisation & tokenisation
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zàèéíòóúïüçñ]+(?:·[a-zàèéíòóúïüçñ]+)*", re.IGNORECASE)
_CONTRACTION_RE = re.compile(r"([ldsmtn])'", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase, NFC-normalise, fold smart quotes, restore Catalan
    middle dot from common typos (l.l → l·l), and collapse triple-letter
    runs (looove → loove)."""
    text = unicodedata.normalize('NFC', text.lower().strip())
    text = (text.replace('’', "'")
                .replace('‘', "'")
                .replace('´', "'"))
    text = re.sub(r'(?<=[a-zà-ú])l[.\-]l(?=[a-zà-ú])', 'l·l', text)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)
    return text


def tokenize(text: str) -> list[str]:
    """Split a normalised string into word tokens (≥ 2 chars)."""
    text = _CONTRACTION_RE.sub(r'\1 ', text)
    return [t for t in _TOKEN_RE.findall(text) if len(t) >= 2]


def split_words(text: str) -> list[str]:
    """Same split as :func:`tokenize` but keeps single-char words.

    Used by callers that need a 1:1 correspondence with input positions —
    e.g. cercador's reconstruction beam, which must preserve filler like
    the Catalan conjunction "i" so reconstructions can exact-match phrase
    index keys that include it.
    """
    text = _CONTRACTION_RE.sub(r'\1 ', text)
    return _TOKEN_RE.findall(text)


# ---------------------------------------------------------------------------
# Top-1000 song authors — hardcoded for the freq-factor boost
# ---------------------------------------------------------------------------
#
# Snapshot of the distinct ``artist`` values appearing in the top-1000 rows
# of ``app/backend/data/processed/top_5000_songs.csv`` (multi-artist cells
# split on commas, first-occurrence order preserved). This list is frozen
# in code intentionally: the parser must not have a data-load dependency
# on the CSV at import time, and ranking should be reproducible across
# environments. Regenerate by re-running the extraction snippet documented
# alongside the CSV if the corpus is refreshed.

_TOP_1000_AUTHORS: tuple[str, ...] = (
    'Lluís Llach',
    'Txarango',
    'Els Pets',
    'De Calaix',
    'Sisa',
    'Els Amics de les Arts',
    'La Gossa Sorda',
    'Companyia El Petit Príncep',
    "Lax'n'Busto",
    'La Ludwig Band',
    'Xesco Boix',
    'Joan Manuel Serrat',
    'Josep Maria Espinàs',
    'Dagoll Dagom',
    'Mainasons',
    'Judit Neddermann',
    'Pau Figueres',
    'Joan Dausà',
    'Figa Flawas',
    'Els Catarres',
    'Raimon',
    "S'Albaida",
    'Siderland',
    'Vers endins',
    "Pep Gimeno 'Botifarra'",
    'Maria del Mar Bonet',
    'Alosa',
    'Banda Neon',
    '31 FAM',
    'Flashy Ice Cream',
    'Oques Grasses',
    "Els Pescadors de L'Escala",
    'Esquirols',
    'Àlex Pérez',
    'Eva Sola',
    'Al Tall',
    'Sau',
    'Ara va de bo',
    'Ginestà',
    'Dani Miquel',
    'La Pataqueta',
    'Club Súper 3',
    'Buhos',
    'Sergi Dantí',
    'Nina',
    'Port Bo',
    'Manel',
    'Ovidi Montllor',
    'Sexenni',
    'Paco Muñoz',
    'La Carxofa i la Ceba amb en Victu Allioli',
    'La Rondalla U.M. la Nucia',
    'Dàmaris Gelabert',
    'Auxili',
    'Naina',
    'La Fúmiga',
    'La Trinca',
    'The Penguins',
    'Manu Guix',
    'Follim Follam',
    'Xavi Lloses',
    'Sopa de Cabra',
    'Toni Giménez',
    'Riu',
    'Teràpia de Shock',
    'Cesk Freixas',
    'Obeses',
    'Sílvia Pérez Cruz',
    'Obrint Pas',
    'Companyia Elèctrica Dharma',
    'Porto Bello',
    'Tacho',
    'Xitxarel·los',
    'Blaumut',
    'Les Absentes',
    'Ramon Calduch',
    'Grup de Folk',
    'Marina Rossell',
    'Música Nostra',
    'Anna Llopart i Xavi G. Cabré',
    'Sandra Monfort',
    'Ferrxn',
    'Guillermina Motta',
    'Titelles i Cançons Pamipipa',
    'Carles Caselles',
    'Salomé',
    'Bajoqueta Rock',
    'Núria Feliu',
    'Pau Riba',
    'Orchestra Fireluche',
    'Cucorba',
    'Jordi Barre',
    "Ja t'ho diré",
    'Ambauka',
    'Habla de mí en presente',
    'La Cobleta de la Selva',
    'Roger Mas',
    'The Companys',
    'Malifeta',
    'Pep Puigdemont',
    'Com sona?',
    'Filibusters',
    'Markos',
    'Emili Vendrell',
    'Corrandes Animació',
    'Sabor de Gràcia',
    'Andrea Motis',
    'Joan Chamorro Group',
    'Guillem Ramisa',
    'Maria Jaume',
    'Uc',
    'La Principal de la Bisbal',
    'Polifònica de Puig-Reig',
    'Els miralls de Dylan',
    'Roger Padrós',
    'Bohemian Betyars',
    'Ultramar',
    'Tomeu Penya',
    'Tito Pontet',
    'La Raíz',
    'Los Chikos Del Maiz',
    'Abril',
    'Baya Baye MGT Los Sosis',
    'Gato Pérez',
    'Roba Estesa',
    'Falsterbo Marí',
    'El Diluvi',
    'Partidaris',
    'Toti Soler',
    'Ester Formosa',
    'Lali BeGood',
    'Viktor Pizza',
    'Maria Hein',
    'Guillem Bautista',
    'Zoo',
    'Josep Carreras',
    'Antònia Font',
    'The Tyets',
    'Mari Dolç',
    'P.A.W.N. Gang',
    'Cris Juanico',
    'Carles Cases',
    'La Bressola – Escoles Catalanes',
    'Quart creixent',
    'Aspencat',
    'Laia Manzanares',
    'Zona Local',
    'Roslyn',
    'Albert Pla',
    'Ju',
    'Alfred García',
    'Ferran Palau',
    'Los Beta Quartet',
    'Dan Peralbo i El Comboi',
    'Duo Dinámico',
    'Al·lèrgiques al pol·len',
    'Miki Núñez',
    'Falsterbo 3',
    'Kelly Isaiah',
    'Anna Andreu',
    'Illi-nois Folk Band',
    'República Ska',
    'Llacuna',
    'Maria Helena Tolosa',
    "El Pont d'Arcalís",
    'Ramon Muntaner',
    'Dyango',
    'David Busquets',
    'Primera Cita',
    'Tralla',
    'FLAKKA',
    'Pastorets Rock',
    'Els Dracs',
    'Peix Fregit',
    'Joan Isaac',
    'Urbàlia Rurana',
    'Lildami',
    'Els de la Torre',
    'Adrià Puntí',
    'Quico el Célio',
    'el Noi i el Mut de Ferreries',
    'Gaietà Renom',
    'Doctor Prats',
    'Frank Montasell',
    'Lydia Torrejón',
    'Margarett',
    'Tremendu',
    'Mariona Escoda',
    'Borja Penalba',
    'Mireia Vives',
    'Cor infantil Verge de Montserrat',
    'Ernest Prana',
    'Judit Farrés',
    'Guillem Roma',
    'Mar Pujol',
    'Tremendamente',
    'Família Picarol',
    'Brams',
    'Macedònia',
    'Luis Aguilé',
    'De Paper',
    'Queta & Teo',
    'Fetus',
    'Filferro',
    'Los Sirgadors',
    'Germà Negre',
    'Stay Homas',
    'JULS',
    'Coral Sant Jordi',
    'Marina Prades',
    'Sr. Chen',
    'Cookah P',
    'Raggattack',
    'Quinto',
    'Jordi Tonietti',
    'Van de kul',
    'Nastallat',
    'Quercus',
    'Els Atrapasomnis',
    'Ana Torroja',
    'Umpah-Pah',
    'Mishima',
    'Dany BPM',
    'Mon Dj',
    '2princesesbarbudes',
    'Remigi Palmero',
    'El Pony Pisador',
    'Rita Payés',
    'Remei de Ca la Fresca',
    'Maria Amèlia Pedrerol',
    'Cinta Massip',
    'Xavier Ribalta',
    'Jaume Arnella',
    'Sangtraït',
    'Torrat i Bullit',
    'Mushkaa',
    "Figues d'un altre paner",
    'The Binigaus Band',
    'Xiula',
    'Joan-Pau Giné',
    'Samantha',
    'Andana',
    'Boom Boom Fighters',
    'Llengua Morta',
    'Gerard Quintana',
    'Mirna',
    'Josmar',
    'Julieta',
    'Biel Majoral',
    'Grimpallunes',
    'Pablo Alborán',
    'En Tol Sarmiento',
    'Maria Arnal i Marcel Bagés',
    'Jo Jet i Maria Ribot',
    'Noa',
    'Les anxovetes',
    'Miquel Gil',
    'Pep Picas',
    'Quimi Portet',
    'Aigua',
    'Gertrudis',
    'El Corral de Pepeta',
    'Teresa Rebull',
    'Pau Vallvé',
    "Rovell d'ou",
    'Aitana',
    'Mercè Madolell',
    'Gossos',
    'Joan Josep Mayans',
    'Gemma Humet',
    'Escola Superior de Música de Catalunya',
    'Maria Laffitte',
    'Els 3 tambors',
    'Rudymentari',
    'Feliu Ventura',
    'Miquel Abras',
    'Will.x.o',
    'Ceaxe',
    'VWAE',
    'Amadeu Casas',
    'Animal',
    'La Colla Pirata',
    'Marc Vilajuana',
    'La Tresca i la Verdesca',
    'Adala',
    'Peret',
    "Anna Roig i l'Ombre de Ton Chien",
    'Amansalva',
    'Bernardino i el seu Grup',
    'Cala Vento',
    'Los Manolos',
    'Ebri Knight',
    'Periferia',
    'Canimas',
    'Família Macià',
    'La Ratonera',
    'Rabadàb',
    'Joan Adrià Pistola',
    'Els Surfing Sirles',
    'Joan-Llorenç Solé',
    'Lo Pardal Roquer',
    'Xerramequ Tiquis Miquis',
    'Núria Lozano',
    'Mak & Sak feat. Xana',
    'Renaldo & Clara',
    'Clara',
    'Rafael Subirachs',
    'Marala',
    'Xanguito',
    'Pilseners',
    'La Pegatina',
    'Dijous Paella',
    'gavina.mp3',
    'Cap Pela',
    'Orquestra Plateria',
    "Els Cantaires de l'Estany",
    'Jimmy Fontana',
    'Romàntic Dimoni',
    'TESA',
    'Jordi Bardella',
    'Emboirats',
    'Es Revetlers',
    'Orfeó Català',
    'K-ZU',
    'Strombers',
    'Jordi Vidal',
    'Álvaro Soler',
    'Celdoni Fonoll',
    'Júlia Colom',
    'roots',
    "Ven'nus",
    'Ai',
    'Herbes Dolces',
    'KOP',
)

# Distinct word-tokens appearing in any author phrase above, run through
# the same normalise+tokenise pipeline the parser applies to query words
# (so lookups against fuzzy candidates and lexicon entries — both already
# lowercased and NFC-normalised — match by string equality). Built once
# at import; a frozenset for O(1) membership in the per-candidate loop.
_AUTHOR_WORDS: frozenset[str] = frozenset(
    tok
    for phrase in _TOP_1000_AUTHORS
    for tok in tokenize(normalize(phrase))
)


def _author_boosted_freq_factor(word: str, freq: float) -> float:
    """Same as :func:`freq_factor`, except a `word` in :data:`_AUTHOR_WORDS`
    is scored as if its raw frequency were FREQ_REF — i.e. the freq factor
    saturates to 1.0. This lifts rare artist surnames (which wordfreq
    barely sees) so corrections aim at them in preference to common-word
    neighbours; stopwords inside artist names are already saturated by
    their natural freq, so the boost is a no-op for them."""
    if word in _AUTHOR_WORDS:
        return freq_factor(FREQ_REF)
    return freq_factor(freq)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser2:
    """
    Lexicon-driven probabilistic parser. See module docstring for the
    formula and the operation-cost schedule.

    Public surface:
        parse(query)         → {candidate: prob} per input word, merged.
        load_lexicon(...)    → fills self.lexicon and the 2-gram index.

    Private helpers:
        _candidates_for_word(w) — full pipeline for a single input word.
        _fuzzy_candidates(w)    — 2-gram inverted-index lookup.
        _oov_freq()             — synthetic frequency for OOV inputs.
    """

    def __init__(self):
        # Lexicon: word → raw frequency (≥ 1). Built by load_lexicon.
        self.lexicon: dict[str, int] = {}

        # 2-gram inverted index over accent-folded lexicon entries.
        # `_lex_2gram[bg]` is the set of words whose folded form contains
        # bigram `bg`. Used to filter fuzzy candidates without scanning
        # 50k+ entries per input word.
        self._lex_2gram: dict[str, set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_lexicon(self, min_zipf: float = 2.4, top_n: int = 100_000) -> None:
        """Fill `self.lexicon` from `wordfreq`'s Catalan list (filtered to
        zipf ≥ min_zipf) and build the 2-gram index used by per-query
        fuzzy matching. Also inject any author tokens from
        :data:`_AUTHOR_WORDS` that wordfreq doesn't know about, so artist
        surnames (e.g. "buhos", "txarango") can surface as fuzzy
        candidates — :func:`_author_boosted_freq_factor` then handles
        ranking, saturating their freq factor to 1.0 regardless of the
        synthetic seed frequency stored here."""
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
            self._index_word(w, freq)

        injected = 0
        for w in _AUTHOR_WORDS:
            if w in self.lexicon:
                continue
            if len(w) < 2 or not re.search(r'[a-zàèéíòóúïüç]', w):
                continue
            self._index_word(w, 1)
            injected += 1
        print(f"[lexicon] {len(self.lexicon):,} words (+{injected} from authors)")

    def _index_word(self, w: str, freq: int) -> None:
        """Add `w` to the lexicon at `freq` and update the folded 2-gram
        index used by :meth:`_fuzzy_candidates`."""
        self.lexicon[w] = freq
        folded = _fold(w)
        for i in range(len(folded) - 1):
            self._lex_2gram[folded[i:i + 2]].add(w)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_per_word(self, query: str) -> list[dict[str, float]]:
        """
        Per-input-word candidate distributions.

        Like `parse`, but preserves the per-word structure instead of
        max-merging across positions. Returned list is parallel to
        `tokenize(normalize(query))` — index i is the normalised
        distribution for word i. Empty list if the query has no tokens.

        Use this when downstream needs the cross-product of per-position
        alternates (e.g. enumerating sentence reconstructions for an
        exact-phrase match boost) — the merged `parse()` output throws
        away which word produced which alternate.
        """
        q = normalize(query)
        words = tokenize(q)
        if not words:
            return []
        return [self._candidates_for_word(w) for w in words]

    def parse(self,
              query: str,
              top_k: int = 20,
              phrase_match: bool = False) -> dict[str, float]:
        """
        Parse a query (one or more words) and return a {candidate:
        probability} dict, sorted by probability and trimmed to top_k.

        Each input word is processed independently; its candidates are
        normalised so they sum to 1 within that word's distribution.
        For multi-word queries we keep the maximum probability per
        candidate across all input words.

        `phrase_match` is accepted for API stability but ignored.
        """
        per_word = self.parse_per_word(query)
        if not per_word:
            return {}

        merged: dict[str, float] = {}
        for dist in per_word:
            for cand, p in dist.items():
                if p > merged.get(cand, 0.0):
                    merged[cand] = p

        ranked = sorted(merged.items(), key=lambda kv: -kv[1])
        return {c: round(p, 4) for c, p in ranked[:top_k]}

    # ------------------------------------------------------------------
    # Per-word pipeline
    # ------------------------------------------------------------------

    def _oov_freq(self) -> float:
        """Synthetic frequency for OOV input. Treated the same as the
        rarest real entry (freq = 1) — the assumption is that an OOV
        word is at least as common as the lexicon's tail, since it
        appeared in real usage (the user typed it). The pre-norm input
        floor (INPUT_RAW_FLOOR) handles the rest."""
        return 1.0

    def _candidates_for_word(self, word: str) -> dict[str, float]:
        """
        Produce the normalised distribution of candidates for a single
        input word.

        Three sources, all contributing raw probabilities to the same
        dict (max per duplicate key) before the final normalisation:

          1. the input word itself, scored as exp(0) · freq_factor
             (OOV inputs use the synthetic prior).
          2. lexicon entries within MAX_WORD_DISTANCE, scored with the
             standard p_raw formula.
          3. pair-of-words splits: every binary split of `word` whose
             two halves are both real lexicon words contributes one
             "left right" key, scored as harmonic_mean(p_left, p_right)
             where each half uses d = SPLIT_COST.
        """
        raw: dict[str, float] = {}

        # 1. Input word itself. exp(0) = 1, so raw[word] is just the
        #    freq factor. We then apply the pre-normalisation floor
        #    INPUT_RAW_FLOOR — niche real words don't get crushed when
        #    every alternate is also weak, but a strong correction will
        #    still dominate after softmax.
        in_lex = self.lexicon.get(word, 0)
        input_freq = in_lex if in_lex > 0 else self._oov_freq()
        raw[word] = max(_author_boosted_freq_factor(word, input_freq), INPUT_RAW_FLOOR)

        # 2. Fuzzy lexicon matches.
        wlen = len(word)
        for cand in self._fuzzy_candidates(word):
            if cand == word:
                continue
            # length pre-filter: with MAX_WORD_DISTANCE = 1.5 and
            # insert/delete = 1.0, the lengths can't differ by more than 1
            # (middle dots are essentially free, so allow extra slack).
            if abs(len(cand) - wlen) > 1 + word.count('·') + cand.count('·'):
                continue
            d = edit_distance(word, cand, cap=MAX_WORD_DISTANCE)
            if d > MAX_WORD_DISTANCE:
                continue
            # L = input length so any two 1-edit candidates get the same
            # exp factor regardless of their own length (e.g. for input
            # "bog", both "bo" and "blog" share L=3, and freq decides).
            p = distance_to_prob(d, wlen) * _author_boosted_freq_factor(cand, self.lexicon[cand])
            if p > raw.get(cand, 0.0):
                raw[cand] = p

        # 3. Pair-of-words splits. Both halves must be in the lexicon
        #    and ≥ 2 chars. Each half is scored as if the input differed
        #    from it by SPLIT_COST = 1.5 (the implicit missing space),
        #    and the pair's joint probability is the geometric mean of
        #    the two — both need to be plausible, but a strong half
        #    partly compensates a weaker one.
        for i in range(2, wlen - 1):
            left, right = word[:i], word[i:]
            f_l = self.lexicon.get(left, 0)
            f_r = self.lexicon.get(right, 0)
            if f_l <= 0 or f_r <= 0:
                continue
            # Reference length is the *original* glued word: the missing
            # space is one global edit, not one per half, so both halves
            # share the same exp factor and only their freqs differ.
            exp_factor = distance_to_prob(SPLIT_COST, wlen)
            p_l = exp_factor * _author_boosted_freq_factor(left, f_l)
            p_r = exp_factor * _author_boosted_freq_factor(right, f_r)
            p_pair = math.sqrt(p_l * p_r)              # geometric mean
            key = f"{left} {right}"
            if p_pair > raw.get(key, 0.0):
                raw[key] = p_pair

        # Softmax normalisation: p_norm = exp(p / T) / Σ exp(p_i / T).
        # Numerically stable form: subtract max(p / T) before exp.
        if not raw:
            return {}
        items = list(raw.items())
        scores = [v / SOFTMAX_T for _, v in items]
        m = max(scores)
        exps = [math.exp(s - m) for s in scores]
        z = sum(exps)
        if z <= 0:
            return {}
        softmaxed = sorted(
            ((items[i][0], exps[i] / z) for i in range(len(items))),
            key=lambda kv: -kv[1],
        )

        # Trim the long tail: keep top-KEEP_TOP_N + anything ≥ PROB_FLOOR,
        # then renormalise so the survivors sum to 1. The list is already
        # sorted descending, so once we hit a candidate that fails *both*
        # conditions we can stop — nothing further can pass either.
        kept: list[tuple[str, float]] = []
        for i, (cand, prob) in enumerate(softmaxed):
            if i < KEEP_TOP_N or prob >= PROB_FLOOR:
                kept.append((cand, prob))
            else:
                break
        total = sum(prob for _, prob in kept)
        if total <= 0:
            return {}
        return {cand: prob / total for cand, prob in kept}

    def _fuzzy_candidates(self, word: str) -> set[str]:
        """Lexicon entries that share at least one accent-folded bigram
        with `word`, plus the swap-corrected mirror so a transposition
        at the start of the word (e.g. amro → amor) still surfaces
        candidates whose first bigram matches the un-swapped form."""
        if not self.lexicon:
            return set()
        folded = _fold(word)
        out: set[str] = set()
        for i in range(len(folded) - 1):
            out.update(self._lex_2gram.get(folded[i:i + 2], ()))
            tr = folded[i + 1] + folded[i]
            out.update(self._lex_2gram.get(tr, ()))
        return out
