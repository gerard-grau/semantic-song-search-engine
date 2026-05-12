# Cercador — Technical Documentation

This document describes the instant-search subsystem (`/api/cercador`) that powers the
Viasona-style search page. It covers the inverted-index retrieval (`cercador_index.py`)
and the probabilistic Catalan spell-checker (`parser2.py`) that feeds it.

The cercador is **lexical, not semantic** — it never touches embeddings. Its job is to
turn a (possibly mistyped) Catalan string into the right songs/bands/articles, with
fuzzy matching that handles typos, missing accents, and missing spaces.

---

## File Map

| File | Purpose |
|------|---------|
| `app/backend/api/routes/cercador.py` | FastAPI route `/api/cercador?q=...`. Calls `get_index().search()`, then `derive_correction()`. |
| `app/backend/core/cercador_index.py` | `CercadorIndex` — three inverted indices over `songs/grups/noticies`, scoring, exact-phrase boosts, phrase rerank. |
| `app/backend/core/parser2.py` | `Parser2` — wordfreq-backed Catalan lexicon, weighted Damerau-Levenshtein, per-word probabilistic query expansion. |
| `app/backend/core/data_loader.py` | `load_all_songs()` — joins `augmented_songs.csv` with `cancons.csv`, restricted to IDs in `embedded_songs.parquet`. |
| `app/backend/data/grups.csv` | Band catalogue. |
| `app/backend/data/noticies.csv` | News articles. |

---

## Request Pipeline

```
GET /api/cercador?q="bog per tu"
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ get_index()  →  CercadorIndex (singleton, built on first request)   │
│   • parser2.load_lexicon()       — wordfreq Catalan, zipf ≥ 2.4     │
│   • _index_songs/_grups/_noticies — token → [(item_idx, field_w)]   │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ index.search(q)                                                     │
│  1. parser.parse(q)         → {token: prob}  (fuzzy expansion)      │
│  2. _score per source       → BM25-idf · lex_penalty · field_w · p  │
│  3. exact-phrase boost      → +50 if q_norm matches a *_phrase key  │
│  4. reconstruction boost    → beam-search per-word alts, exact-     │
│                               match each survivor against phrases   │
│  5. _phrase_rerank top-120  → +distance_to_prob(DL(q, phrase)) · w  │
│  6. _top per source         → dedup-by-normalized-key, take K       │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ derive_correction(q, parsed, index)                                 │
│   For each input word not in catalog_tokens AND not common Catalan, │
│   take the top alt from `parsed` if prob ≥ 0.6.                     │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
   { grups, cancons, noticies, correction }
```

---

## Parser2 — query expansion

Parser2 is a **lexicon-only probabilistic spell-checker**. It does not look at the
catalog. Given an input word it returns a probability distribution over what the user
might have meant.

### Lexicon

`load_lexicon(min_zipf=2.4, top_n=100_000)` pulls `top_n_list('ca', 100_000)` from
`wordfreq`, filters by zipf ≥ 2.4, and stores `lexicon[w] = int(word_frequency * 1e6)`
(per-million scale). It also builds `_lex_2gram`: every accent-folded bigram maps to
the set of lexicon words containing it. This is what makes per-query fuzzy expansion
fast — `_fuzzy_candidates(word)` returns the union of bigram buckets (plus their
swap-mirrors) instead of scanning the whole lexicon.

### Weighted Damerau-Levenshtein

`edit_distance(a, b, cap)` (parser2.py:219) uses a custom cost schedule:

| Operation | Cost |
|-----------|------|
| Adjacent transposition (`amro ↔ amor`) | 0.5 |
| Accent-only / fold-equivalent (`é ↔ e`, `ç ↔ c`, middle-dot insert/delete) | 0.1 |
| Substitution, keys adjacent on QWERTY (same row, one column apart) | 0.85 |
| Substitution, keys not adjacent | 1.5 |
| Insert / delete | 1.0 |
| Space | 2.0 |

The `cap` parameter does a row-min early exit — every row that exceeds `cap` returns
`cap + 1.0`, so callers can cheaply skip hopeless candidates. This is what makes
`_phrase_rerank` cheap.

### Per-word distribution

For each input word, three sources contribute raw probabilities:

1. **The input word itself.** `raw[word] = max(freq_factor(input_freq), INPUT_RAW_FLOOR=0.20)`. OOV inputs use a synthetic frequency. The floor stops niche real words (dialect, proper nouns absent from wordfreq) from being crushed when alternates are also weak.
2. **Fuzzy lexicon matches.** For every bigram-bucket candidate within `MAX_WORD_DISTANCE = 1.75`: `p = exp(-DECAY · d / len(word)) · freq_factor(lexicon[cand])`. Reference length is the *input* length — two 1-edit candidates of different lengths get the same exp factor, frequency picks the winner.
3. **Pair-of-words splits.** For every binary split where both halves are lexicon words, charge `SPLIT_COST = 1.5` once globally and score the pair as `sqrt(p_left · p_right)`. This is how `"moltbe"` recovers `"molt be"`.

Then softmax with `T = 0.10` (sharp), trim to top-5 plus anything ≥ 0.20, renormalise.
Tuned so a correctly-typed common word ends up ≥ 90% of its own distribution's mass.
The top-5 (rather than top-3) rank rule gives some slack to candidates that wordfreq
underrates relative to this domain — e.g. `boig` (per-million freq 13) survives next
to common short words like `bo` (135), `bon` (457) for the input `bog`, so a catalog
match downstream can still resolve the ambiguity.

### Public surface

| Method | Returns | Used by |
|--------|---------|---------|
| `parse(q, top_k=20, phrase_match=False)` | flat `{candidate: prob}`, max-merged across positions | `_score` for posting-list scan |
| `parse_per_word(q)` | list of per-position distributions | `_enumerate_reconstructions` beam search |
| `lexicon` | `{word: per-million-freq}` | `_score` lex penalty, `derive_correction` known-word check |

---

## CercadorIndex — retrieval

### Indices

For each source (`songs`, `grups`, `noticies`) the index stores three structures:

| Structure | Type | Used for |
|-----------|------|----------|
| `<source>_idx` | `dict[token → list[(item_idx, field_weight)]]` | Posting-list scoring |
| `<source>_phrase` | `dict[normalized_full_phrase → list[item_idx]]` | Exact-phrase boosts |
| `_<source>_*_norm` | `list[str]` parallel to items | `_phrase_rerank` reads `phrase = norm_phrases[idx]` |

### Field weights

```
W_SONG_TITLE   = 1.6     W_GRUP_NAME    = 1.6
W_SONG_ARTIST  = 1.3     W_NOTI_TITLE   = 1.6
W_SONG_LYRICS  = 0.4     W_NOTI_SNIPPET = 0.4
```

### Stopword handling (asymmetric)

A built-in `_STOPWORDS` set covers Catalan articles, prepositions, conjunctions,
auxiliaries, and clitics — including accented variants (`mes`/`més`) since
`normalize()` keeps accents.

- **Indexing**: title/name fields index *all* tokens (including stopwords). Snippet/lyrics fields filter stopwords and cap at 25 unique tokens per item, so `"de"/"la"` don't drown out real signal.
- **Querying**: stopword filter is on by default in `_score`. It flips off automatically when *every* query token is a stopword (`"pel"`, `"el meu"`), so the all-stopword fallback still retrieves something.

### Scoring

```python
idf = max(0.1, log((N - df + 0.5) / (df + 0.5)))           # BM25 idf
lex_penalty = 1.0 / (1.0 + lexicon.get(tok, 0) / 100.0)    # LEX_PENALTY_REF
score[item] += prob · idf · lex_penalty · field_weight
```

Three independent dampeners, each catching what the others miss:

| Multiplier | Source | Catches |
|------------|--------|---------|
| `prob` | Parser2 | Typos, missing accents, missing spaces |
| `idf` | corpus df | Tokens that happen to flood *this* catalog (e.g. a band name in 800 titles) |
| `lex_penalty` | wordfreq | Grammatical filler in Catalan (`pel`) that isn't statistically dominant in the catalog |

The 0.1 idf floor matters: tokens past ~50% df would go negative, so the floor stops a
near-universal token from actively *demoting* matches. Multi-word matches still beat
single-word ones because they accumulate floors from multiple positions.

### Exact-phrase boost (literal)

```python
for i in songs_title_phrase.get(q_norm, ()):
    song_scores[i] += EXACT_PHRASE_BOOST  # 50.0
```

`50.0` is orders of magnitude above typical token scores, so an exact match on a band
name will essentially always win. Artist matches get half (`25.0`) because artist
confusion is more common than band confusion.

### Exact-phrase boost (reconstruction)

The literal boost only fires if the user typed the phrase exactly. To catch
`"comel dia i lanit" → "Com el dia i la nit"`, `_enumerate_reconstructions` runs a
beam search over `parser.parse_per_word(query)`:

- Position alignment uses `split_words(normalize(query))` rather than `tokenize`, so single-char tokens (the Catalan conjunction `"i"`, etc.) keep their position. Those short positions are pinned to a `{w: 1.0}` singleton since Parser2 doesn't score them. Without this the indexed phrase `"com el dia i la nit"` could never be exact-matched from a query where `"i"` would otherwise be dropped.
- Beam holds `(phrase, log_prob)`.
- Per-word fan-out: `RECONSTRUCT_TOP_PER_WORD = 5` alternates per position.
- Beam width: `RECONSTRUCT_BEAM_K = 32`.
- Survivor floor: joint prob ≥ `RECONSTRUCT_MIN_JOINT_PROB = 0.05`.

Each survivor is exact-matched against `*_phrase` dicts and gets the full
`EXACT_PHRASE_BOOST`. The joint-probability floor is the "high enough probability"
gate — anything past it deserves the boost.

The fan-out of 5 (rather than 3) matters in the same way the per-word `KEEP_TOP_N = 5`
does: a low-frequency-but-domain-correct candidate like `boig` (rank 5 in `bog`'s
distribution at ~9%) still enters the beam, where joint prob `≈ 0.09 × 0.99 × 0.99
≈ 0.09 > 0.05` survives the floor and triggers the boost on `"Boig per Tu"`.

### Phrase rerank

`_phrase_rerank` runs only for multi-token queries (single-token queries should match
items *containing* the token, not items of similar total length). For each source it
pulls the top-120 candidates by current score and adds:

```python
distance_to_prob(edit_distance(q_norm, phrase, cap=4.0), max_len) · weight
```

Weights: song title 18, grup name 18, song artist 12, noticia title 12. Two
prefilters keep this cheap — a length-gap check and the `cap` early exit on
`edit_distance`. Total cost is ~5 ms for 120 candidates, independent of catalog size.

### Top-K with dedup

`_top` sorts all scored items, then walks in score order keeping the first occurrence
per dedup key. Songs dedup on `(normalized_title, normalized_artist)`; grups on
`normalized_name`; noticies on `(normalized_title, date)`. This is necessary because
the source CSVs have logical duplicates (e.g. `augmented_songs` has repeated
`id_lyrics` rows).

---

## derive_correction — the spell-fix UX

After scoring, the route surfaces a correction *only* when at least one input word is
neither in the catalog nor a common Catalan word:

```python
def _word_is_known(w):
    return w in catalog_tokens or lexicon.get(w, 0) >= 200
```

For each unknown word, alternates are pulled from the merged `parsed` dict, filtered
to single-word candidates (pair candidates aren't useful for per-word correction),
ranked by probability. If the top alt has `prob ≥ 0.6`, the corrected word replaces
the input. Two additional phrasings are built from the 2nd and 3rd alternates.

`catalog_tokens` is built once at index build time from all titles/names/artists, so
the guard works without re-tokenising the catalog per request.

---

## End-to-end trace — `"bog per tu"`

1. **Route** (`cercador.py:67`) calls `get_index().search("bog per tu")`.
2. **Parser** produces (per-position, before merge): for `bog` → `{bo: 0.36, blog: 0.23, bon: 0.18, bog: 0.14, boig: 0.09}`; for `per` → `{per: ~1.0}`; for `tu` → `{tu: ~1.0}`. Merged via `max`-per-candidate, the parsed bag includes `boig` at 0.09 and the rest near their per-position values.
3. **`_score`** runs over each source. `boig` has low df + low lex frequency → high BM25 idf, near-1.0 lex_penalty → its contribution to `"Boig per Tu"` is `0.09 · idf(boig) · 0.88 · 1.6`, modest but non-zero. `per`/`tu` are flooded → idf clamped to the 0.1 floor, lex_penalty crushed by `lex.get("per") ≈ 300` → tiny additive contributions on every song with `per`/`tu` in title or artist. After `_score` the target song has a moderate (not dominant) score against everything else with `per` or `tu` in it.
4. **Literal-phrase boost**: `q_norm = "bog per tu"` is not in `songs_title_phrase`, so no boost.
5. **Reconstruction boost**: the beam expands all 5 alternates at position 0 against `per`/`tu`'s single dominant candidates. Survivors include `"bo per tu"` (jp ≈ 0.35), `"blog per tu"` (jp ≈ 0.23), …, `"boig per tu"` (jp ≈ 0.09). Only `"boig per tu"` matches a `songs_title_phrase` key, so the song gets `+50.0` — orders of magnitude above the bag-of-words score. **This is what actually locks in the win.**
6. **`_phrase_rerank`** runs (3 tokens, multi-token gate passed). The song is already in the top-120 thanks to the +50 boost. `edit_distance("bog per tu", "boig per tu") = 1.0` (one insert), so `distance_to_prob(1.0, 11) · 18 ≈ 13.4` is added on top. Cosmetic at this point.
7. **`_top`** returns the deduped top-K per source.
8. **`derive_correction`**: For `bog` (not in `catalog_tokens`, not common Catalan), the parsed alts ranked by prob start with `bo` (0.36), `blog` (0.23), `bon` (0.18), `boig` (0.09). With `min_alt_prob=0.6` none clears the gate, so no correction is surfaced. The search still returns the right song — it just doesn't tell the user "did you mean…".

Note the asymmetry in step 8: under wordfreq alone, `bo` looks more likely than `boig`,
so the correction UX doesn't fire. The *search* result is still correct because the
reconstruction-boost path lets a low-probability catalog candidate win on phrase
identity. If you want `derive_correction` to also reach `boig`, the right lever is the
catalog prior — boost candidates that appear in `catalog_tokens` before softmax.

---

## Lifecycle

- The index is a module-level singleton (`cercador_index._INDEX`).
- `get_index()` builds on first call (~5-10s for lexicon + catalog).
- `prewarm()` is invoked from FastAPI's `lifespan` so the first user request doesn't pay that cost.
- `parser.lexicon` and `catalog_tokens` live inside the same singleton — `derive_correction` reads both without extra wiring.

---

## Tuning knobs (quick reference)

| Constant | Default | Effect |
|----------|---------|--------|
| `parser2.MAX_WORD_DISTANCE` | 1.75 | Per-word edit-distance budget for fuzzy candidates. Higher → more typo tolerance, more noise. |
| `parser2.MAX_PHRASE_DISTANCE` | 4.0 | Cap on `_phrase_rerank`'s `edit_distance` call. |
| `parser2.DECAY` | 3.0 | Steepness of the `exp(-DECAY · d / L)` curve. Higher → input word dominates more. |
| `parser2.SOFTMAX_T` | 0.10 | Lower → sharper per-word distribution (top candidate dominates more). |
| `parser2.INPUT_RAW_FLOOR` | 0.20 | Pre-softmax floor on the input word's raw probability. |
| `parser2.KEEP_TOP_N` / `PROB_FLOOR` | 5 / 0.20 | Long-tail trim on each per-word distribution. The rank rule keeps the top-5 even if their probabilities fall below the floor. |
| `cercador_index.EXACT_PHRASE_BOOST` | 50.0 | Additive boost on exact-phrase hits. |
| `cercador_index.LEX_PENALTY_REF` | 100 | wordfreq-based dampener reference (per-million). |
| `cercador_index.RECONSTRUCT_BEAM_K` | 32 | Beam width for sentence reconstruction. |
| `cercador_index.RECONSTRUCT_TOP_PER_WORD` | 5 | Per-word fan-out into the beam. Kept in sync with `KEEP_TOP_N` so a candidate that survives Parser2's trim can actually enter reconstructions. |
| `cercador_index.RECONSTRUCT_MIN_JOINT_PROB` | 0.05 | Drop reconstructions below this joint probability. |

---

## Response shape

```json
{
  "grups":      [{ "id", "name", "song_count", "viasona_link", "foto", "municipi", "regio", "genres" }],
  "cancons":    [{ "id", "title", "artist", "lyrics_snippet", "genre", "url" }],
  "noticies":   [{ "id", "title", "snippet", "date", "viasona_link" }],
  "correction": null | { "corrected": "boig per tu", "suggestions": [...] }
}
```
