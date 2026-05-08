"""
Console REPL for parser2.

Loads only the wordfreq Catalan lexicon (parser2 is lexicon-only — no
catalog) and lets you type queries to inspect the probability
distribution the parser produces.

Run from the project root:
    python3 test_parser2.py

Commands inside the REPL:
    <query>          → parse the query, show ranked candidates
    !info <word>     → lexicon membership / frequency for one word
    !q / !quit       → exit
"""

from __future__ import annotations

import sys
import time

from app.backend.core.parser2 import (
    MAX_WORD_DISTANCE,
    Parser2,
    edit_distance,
    freq_factor,
    normalize,
    tokenize,
)


def _kind(cand: str) -> str:
    return "pair" if " " in cand else "word"


def explain(parser: Parser2, query: str) -> None:
    q_norm = normalize(query)
    words = tokenize(q_norm)

    t0 = time.perf_counter()
    parsed = parser.parse(query)
    dt_ms = (time.perf_counter() - t0) * 1000

    print(f"\n  normalized: {q_norm!r}   tokens: {words}   ({dt_ms:.1f} ms)")
    print(f"  → {len(parsed)} candidate(s) (probabilities sum to 1 per "
          f"input word, max-merged across words):\n")
    if not parsed:
        print("    (none)")
        return

    print(f"    {'candidate':<24}{'p':>7}  {'freq':>9}  {'ff':>5}  "
          f"{'min_d':>6}  type")
    print("    " + "-" * 78)
    for cand, p in parsed.items():
        if " " in cand:
            # Pair: report the worse half so it's obvious which side is
            # holding the joint probability down.
            halves = cand.split(" ")
            freqs = [parser.lexicon.get(h, 0) for h in halves]
            freq_disp = "/".join(str(f) for f in freqs)
            ff_min = min(freq_factor(f) for f in freqs)
            d_disp = "—"
            print(f"    {cand:<24}{p:>7.4f}  {freq_disp:>9}  "
                  f"{ff_min:>5.2f}  {d_disp:>6}  pair")
        else:
            f = parser.lexicon.get(cand, 0)
            freq_disp = str(f) if f > 0 else "OOV"
            ff_disp = freq_factor(f) if f > 0 else freq_factor(parser._oov_freq())
            min_d = min(
                (edit_distance(w, cand, cap=MAX_WORD_DISTANCE) for w in words),
                default=0.0,
            )
            print(f"    {cand:<24}{p:>7.4f}  {freq_disp:>9}  "
                  f"{ff_disp:>5.2f}  {min_d:>6.2f}  word")


def info(parser: Parser2, word: str) -> None:
    w = normalize(word)
    freq = parser.lexicon.get(w, 0)
    print(f"\n    word:        {w!r}")
    print(f"    in_lexicon:  {freq > 0}")
    if freq > 0:
        print(f"    lexicon[w]:  {freq}")
        print(f"    freq_factor: {freq_factor(freq):.3f}")
    else:
        oov = parser._oov_freq()
        print(f"    OOV — would use synthetic prior: "
              f"freq={oov:.2f}, ff={freq_factor(oov):.3f}")


def main() -> int:
    print("Loading wordfreq Catalan lexicon (~50k words)…")
    t0 = time.time()
    parser = Parser2()
    parser.load_lexicon(min_zipf=2.4)
    print(f"Ready in {time.time() - t0:.1f}s — {len(parser.lexicon):,} words.\n")

    print("Commands:")
    print("  <query>         — parse, show candidate probabilities")
    print("  !info <word>    — lexicon membership / frequency")
    print("  !q / !quit      — exit")
    print()

    while True:
        try:
            line = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("!q", "!quit", "q", "quit", "exit"):
            return 0
        if line.startswith("!info "):
            info(parser, line[len("!info "):].strip())
            continue
        explain(parser, line)


if __name__ == "__main__":
    sys.exit(main())
