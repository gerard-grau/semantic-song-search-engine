# 05 — `searchoptimal/` — parser de cerca textual

Llibreria pura (sense Flask/FastAPI) que implementa el parser tipus
"Did you mean / autocomplete" emprat per `/api/cercador`.

## Fitxers

| Fitxer | Estat | Funció |
| --- | --- | --- |
| `parser.py` | **Actiu** | Parser principal (`CatalanSongQueryParser`). Importat per `cercador.py`. |
| `parser2.py` | **Codi mort** | Versió alternativa (Damerau-Levenshtein amb costos per teclat). No s'importa enlloc. Es manté com a referència; veure `10_codi_mort_i_millores.md`. |
| `catalog.py` | Demo | Catàleg llavor (`SONGS`) per executar `python parser.py` sense backend. |

---

## `parser.py` — `CatalanSongQueryParser`

Pipeline en tres fases. Cada fase pot afegir candidats al "pool" final. El
millor candidat (per `score`) es retorna com a `corrected`; els k-1 següents
com a `suggestions`.

### Fase 1 — Normalització trivial

`normalize(text)` aplica, en aquest ordre:

1. NFC (composa accents si la font és descomposada).
2. Lowercase + strip.
3. `’ ‘ ´` → `'` (smart-quotes).
4. Patrons de l·l: `l.l`, `l-l` → `l·l`.
5. Triple-letter collapse: `looool` → `lool`.

`fold_accents(text)` tira els combinants Unicode i fa `ç → c`, `· → ""` per
indexar versions sense diacrítics. La indexació "doble" (amb i sense accents)
permet correccions tipus `cancio → cançó` a distància 0.

`tokenize(text)` separa contraccions (`l'amor → l amor`) i extreu lletres
catalanes amb suport per `·` interior.

### Fase 2 — Frase sencera

S'intenten quatre estratègies en paral·lel:

| Estratègia | Tier | Exemple |
| --- | --- | --- |
| `_phrase_match` | 11/12 | `"boig per tu"` → `Sau / Boig per tu` |
| `_completions` | 10/11 | `"boig per"` → `Boig per tu` |
| `_split_match` | 11 | `"sau boig per tu"` → `Sau` + `Boig per tu` |
| `_artist_expansions` | 9 | `"lluis llach"` → `Lluís Llach L'estaca` |

Cada candidat porta `(text, distance, tier, freq)` i es puntua:

```
score = tier * 10_000 − distance * 100 + log1p(freq)
```

Així una coincidència de tier `ARTIST_PHRASE` (12) a distància 4 (≈119 600)
encara guanya una correcció lèxica perfecta (10 000) — això és el "weight
titles and authors much more".

### Fase 3 — Fallback per token

Només si cap candidat de fase 2 supera un threshold de confiança (distància
≤ ~q_len/4 i tier ≥ TIER_COMPLETION_TITLE), s'aplica
`_token_sequence_correction`: corregeix cada token independentment contra
els tres índexs (artista, títol, lèxic generic) i uneix.

### Fitxer-segmentació

Si la query és un blob sense espais (`boigpertu`), `_word_segment` intenta
trencar-lo amb `SymSpell.word_segmentation` només si no hi ha cap correcció
fuzzy d'una sola paraula al voltant. Filtra els segments resultants per
freqüència mínima — això evita splits absurdament fragmentats com
`"lib el lula"`.

### Constants i tunings

| Constant | Valor | Què controla |
| --- | --- | --- |
| `MAX_ED_PHRASE` | 4 | Distància màxima absoluta per coincidències de frase. |
| `MAX_ED_TOKEN` | 2 | Distància màxima per coincidències per paraula. |
| `MIN_TOKEN_LEN_FOR_CORRECTION` | 3 | Tokens més curts no es corregeixen. |
| `SUGGESTION_SCORE_GAP` | 25 000 | Gap màxim entre el guanyador i les suggerències mostrades. |
| `MIN_WORD_WEIGHT` | 0.30 | Pes mínim per a una paraula al "word bag". |
| `ORIGINAL_WORD_WEIGHT` | 0.50 | Pes garantit per a les paraules originals de la query. |
| `MIN_SEGMENT_PART_FREQ` | 10 | Freq mínima d'un fragment per justificar una segmentació. |

`adaptive_max_ed(text_len, cap)` retorna 0/1/2/3/4 segons longitud per evitar
correccions agressives en paraules curtes.

### Classe `_Index`

Estructura interna que manté un parell `SymSpell` (acentuat + folded) +
`fold_map`. `add(text, freq)` registra l'entrada en ambdós índexs. `lookup`
retorna primer dels candidats del folded i després dels accentuats — això és
el que dóna gratis la insensibilitat d'accents.

### `parse(query, top_k_suggestions=4) → dict`

Sortida:

```python
{
  "original":       "buos",
  "normalized":     "buos",
  "corrected":      "Buhos",
  "suggestions":    ["Buhos Coco", ...],
  "matched_artist": "Buhos",
  "matched_title":  None,
  "words":          {"buhos": 1.0, "buos": 0.5},  # bag of words amb pesos
  "tier":           "artist_phrase",
  "distance":       1,
  "score":          120000.0 - 100 + log1p(...),
  "confident":      True
}
```

`words` és un *bag-of-words probabilístic*: cada paraula té un pes
`score / top_score` indicant la confiança que l'usuari es referia a aquesta
paraula. Inclou les paraules originals (sempre amb `ORIGINAL_WORD_WEIGHT`)
més les paraules dels candidats fins al gap de score.

---

## `catalog.py`

Llista hardcoded `SONGS: list[dict]` amb ~150 cançons icòniques (Lluís Llach,
Sau, Sopa de Cabra, Manel, etc.). Es fa servir només per executar
`python searchoptimal/parser.py` directament i tenir un demo interactiu sense
muntar tot el backend.

`unique_artists()` retorna els artistes únics ordenats.

---

## Diferències amb `parser2.py` (no actiu)

`parser2.py` proposa una arquitectura alternativa basada en
**Damerau-Levenshtein amb costos per operació diferents**, on les
substitucions tenen un cost que depèn de la distància de teclat QWERTY entre
les tecles. La sortida és un mapa simple `{paraula: probabilitat ∈ (0, 1]}`
sense la noció de tiers.

Pros (vs `parser.py`):
- Una sola passada, sense tier system.
- Modela típiques de teclat (lletres adjacents → cost baix).

Contres:
- No té estratègies "complete" / "split" / "artist expansion".
- No retorna entitats detectades (`matched_artist` / `matched_title`).

Si mai s'integra, caldria substituir el contracte de `cercador.py` (que avui
depèn de `parsed["matched_artist"]` etc.).
