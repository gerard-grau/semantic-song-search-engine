# `app/backend/core/parser2.py`

Parser probabilístic de query catalana. Per cada paraula d'entrada retorna una distribució `{candidat: probabilitat}` que combina la paraula tal qual, alternatius del lèxic dins d'un pressupost d'edits, i parells de paraules reals (espais perduts).

## Costos d'edició

Implementació de Damerau-Levenshtein ponderada (en `edit_distance`). Costos exposats per `config.py`:

| Operació | Variable | Valor | Comentari |
| --- | --- | --- | --- |
| Transposició adjacent | `COST_SWAP` | 0.5 | `amro ↔ amor` |
| Inserció | `COST_INSERT` | 1.0 | falta un caràcter |
| Esborrat | `COST_DELETE` | 1.0 | sobra un caràcter |
| Substitució QWERTY adjacent | `COST_SUB_ADJ` | 0.85 | `d ↔ s`, `n ↔ m`… |
| Substitució no adjacent | `COST_SUB_FAR` | 1.5 | qualsevol altra |
| Equivalència d'accent / `ç ↔ c` / `·` | `COST_ACCENT` | 0.1 | manté families |
| Espai explícit | `COST_SPACE` | 2.0 | "molt be" vs "moltbe" |

## Constants de probabilitat

| Variable | Significat |
| --- | --- |
| `DECAY` | Pendent del `exp(-DECAY · d / L)` per la probabilitat bruta. |
| `FREQ_REF` | log1p(f) / log1p(FREQ_REF) saturat a 1 → multiplicador `freq_factor`. |
| `SOFTMAX_T` | Temperatura del softmax per-paraula (més baix → més punta). |
| `KEEP_TOP_N`, `PROB_FLOOR`, `INPUT_RAW_FLOOR` | Sostres i terres per tallar la cua. |
| `SPLIT_COST` | Cost del "espai perdut" als parells de paraules. |
| `MAX_WORD_DISTANCE`, `MAX_PHRASE_DISTANCE` | Pressupostos d'edit-distance per paraula i per frase. |

## Funcions de mòdul

| Nom | Què fa |
| --- | --- |
| `normalize(text)` | Lowercase + NFC + correccions d'apostrofs i `l·l` i collapse de repeticions triples. |
| `tokenize(text)` | Split per regex de paraules catalanes (≥2 chars). |
| `split_words(text)` | Igual però conserva monocaràcters (per al beam de reconstrucció). |
| `edit_distance(a, b, cap=∞)` | DL ponderat amb sortida primerenca via `cap`. |
| `substitution_cost(a, b)` | Decideix entre `0.0 / COST_ACCENT / COST_SUB_ADJ / COST_SUB_FAR`. |
| `freq_factor(freq)` | Mapping log1p saturat. |
| `distance_to_prob(d, ref_len)` | `exp(-DECAY · d / max(L, 2))`. |
| `_fold(text)` / `_fold_char(ch)` | Strip accents + `ç → c`. |
| `_qwerty_adjacent(fa, fb)` | True si dues lletres folded són veïnes horizontals al QWERTY. |

## Classe `Parser2`

| Mètode | Què fa |
| --- | --- |
| `__init__()` | Crea `lexicon` buit i el 2-gram index. |
| `load_lexicon(min_zipf=2.4, top_n=100_000)` | Omple `lexicon` amb `wordfreq` (català). Construeix l'invertit per bigrames d'entrades folded. |
| `parse(query, top_k=20, phrase_match=False)` | Distribució merged (max per candidat) entre totes les paraules. `phrase_match` és ignorat. |
| `parse_per_word(query)` | Llista de distribucions paralel·la a `tokenize(normalize(query))`. |

### Pipeline per paraula (`_candidates_for_word`)

1. **La paraula mateixa.** `freq_factor(freq)` o `INPUT_RAW_FLOOR` per al pis.
2. **Veïns del lèxic** dins `MAX_WORD_DISTANCE`. Pre-filtrats per la unió dels 2-grams folded.
3. **Parells `left right`** que siguin tots dos del lèxic (mitjana geomètrica de les seves probabilitats sota `SPLIT_COST`).
4. **Softmax** per temperatura, trim per `KEEP_TOP_N`/`PROB_FLOOR`, re-normalització.

### Helpers privats

| Nom | Què fa |
| --- | --- |
| `_oov_freq()` | Prior freq per a una paraula no al lèxic. |
| `_fuzzy_candidates(word)` | Veïns del lèxic que comparteixin almenys un bigrama folded (o el seu swap). |
