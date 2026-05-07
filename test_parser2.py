"""
Console REPL for parser2 against the *real* catalog (the same titles,
artists, group names and news titles the live backend loads).

Run from the project root:
    python3 test_parser2.py

Commands inside the REPL:
    <query>          → parse the query, show ranked candidates
    !info <word>     → membership + frequency for a single word
    !cat <substring> → list catalog tokens containing a substring
    !q / !quit       → exit
"""

from __future__ import annotations

import math
import sys
import time

from app.backend.core.cercador_index import get_index
from app.backend.core.parser2 import (
    MAX_WORD_DISTANCE,
    _fold,
    distance_to_prob,
    edit_distance,
    freq_factor,
    normalize,
    tokenize,
)


def _regime(in_cat: bool, freq: int) -> str:
    """
    Word-fuzzy is lexicon-only now. We still report catalog membership
    here (for diagnostic context) but it doesn't affect scoring.
    """
    if freq <= 0:
        return "OOV (not in lexicon)" + (" — but in catalog" if in_cat else "")
    return "lexicon" + (" + catalog" if in_cat else "")


def explain(parser, query: str) -> None:
    q_norm = normalize(query)
    words = tokenize(q_norm)

    t0 = time.perf_counter()
    parsed = parser.parse(query, phrase_match=False)
    dt_ms = (time.perf_counter() - t0) * 1000

    print(f"\n  normalized: {q_norm!r}   tokens: {words}   ({dt_ms:.1f} ms)")
    print(f"  → {len(parsed)} candidate(s):\n")

    if not parsed:
        print("    (none)")
        return

    print(f"    {'word':<22}{'p':>6}  {'in_cat':<7}{'freq':>7}  "
          f"{'ff':>5}  {'min_d':>6}  regime")
    print("    " + "-" * 86)
    for cand, p in parsed.items():
        in_cat = cand in parser.catalog_tokens
        freq = parser.lexicon.get(cand, 0)
        ff = freq_factor(freq) if freq > 0 else 0.0
        # Closest input word, just so the user can see why this candidate
        # surfaced for this query.
        d = min(
            (edit_distance(w, cand, cap=MAX_WORD_DISTANCE) for w in words),
            default=0.0,
        )
        print(f"    {cand:<22}{p:>6.3f}  {str(in_cat):<7}{freq:>7}  "
              f"{ff:>5.2f}  {d:>6.2f}  {_regime(in_cat, freq)}")


def info(parser, word: str) -> None:
    w = normalize(word)
    in_cat = w in parser.catalog_tokens
    freq = parser.lexicon.get(w, 0)
    print(f"\n    word:        {w!r}")
    print(f"    in_catalog:  {in_cat}  (informational — not used in scoring)")
    print(f"    lexicon[w]:  {freq}")
    print(f"    freq_factor: {freq_factor(freq):.3f}")
    print(f"    folded:      {_fold(w)!r}")
    print(f"    regime:      {_regime(in_cat, freq)}")


def cat_search(parser, substring: str, limit: int = 40) -> None:
    sub = substring.lower()
    hits = sorted(t for t in parser.catalog_tokens if sub in t)
    print(f"\n    {len(hits)} catalog tokens containing {sub!r}:")
    for t in hits[:limit]:
        freq = parser.lexicon.get(t, 0)
        print(f"      {t}    (lex_freq={freq})")
    if len(hits) > limit:
        print(f"      … ({len(hits) - limit} more)")


def main() -> None:
    print("Building real catalog + lexicon (this can take ~30-90 s on first run)…")
    t0 = time.time()
    parser = get_index().parser
    print(f"Ready in {time.time() - t0:.1f}s — "
          f"{len(parser.catalog_tokens):,} catalog tokens, "
          f"{len(parser.lexicon):,} lexicon words.\n")

    print("Type a query, or one of:")
    print("  !info <word>    — show membership + freq for one word")
    print("  !cat <sub>      — list catalog tokens containing <sub>")
    print("  !q / !quit      — exit")

    while True:
        try:
            line = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in ("!q", "!quit", "q", "quit", "exit"):
            return
        if line.startswith("!info "):
            info(parser, line[len("!info "):].strip())
            continue
        if line.startswith("!cat "):
            cat_search(parser, line[len("!cat "):].strip())
            continue
        explain(parser, line)


if __name__ == "__main__":
    sys.exit(main() or 0)
