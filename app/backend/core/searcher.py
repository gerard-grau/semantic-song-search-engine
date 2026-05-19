"""
Cercador instantani — búsqueda eficient sobre les dades reals.

Aquest mòdul carrega les tres fonts de dades del catàleg de Viasona
(`cancons.csv`, `grups.csv`, `noticies.csv`) i en construeix índexs
invertits en memòria. La consulta de l'usuari es passa per `Parser2`
(typo-correction + accent-folding + segmentació) i les paraules
candidates resultants es busquen a cada índex; els resultats s'agreguen
per registre i s'ordenen per puntuació.

Característiques clau:

* Una sola càrrega de CSV per procés (lazy-singleton). Al voltant d'un
  segon per arxiu, una vegada.
* Tokenització i normalització compartides amb `parser2.py` per
  garantir que l'índex i la cerca veuen el mateix vocabulari.
* La cerca és O(|tokens_consulta|) per *index hits* + un escaneig
  substring barat sobre els camps curts (títol/artista/nom/títol-noticia)
  per gestionar prefixos del tipus "bo" → "boig".
* Resultats limitats per dataset (5 grups, 8 cançons, 5 notícies, com el
  frontend espera).
"""

from __future__ import annotations

import csv
import logging
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

from app.backend.core.parser2 import Parser2, _fold, normalize, tokenize

logger = logging.getLogger(__name__)

# Some lyric/article fields are very long.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_RAW_DIR  = _DATA_DIR / "raw"
_CANCONS  = _RAW_DIR / "cancons.csv"
_GRUPS    = _RAW_DIR / "grups.csv"
_NOTICIES = _RAW_DIR / "noticies.csv"

# Pesos per camp dins de cada dataset. Un hit al títol / nom val més que
# un hit al cos del text. Multiplica la probabilitat retornada pel parser.
_W_TITLE   = 3.0
_W_ARTIST  = 2.5
_W_NAME    = 3.0
_W_LYRICS  = 0.6
_W_BODY    = 1.0   # snippet / entrada / subtitol / descripcio

# Threshold per considerar una paraula del parser com a "correcció" de
# la consulta original (per al missatge "Volies dir").
_CORRECTION_PROB = 0.55


def _safe(s) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    if s in ("nan", "NaN", "None"):
        return ""
    return s


def _read_csv(path: Path, encoding: str = "utf-8") -> list[dict]:
    """Lector tolerant: salta files malformades o amb columnes desquadrades."""
    if not path.exists():
        logger.warning("CSV not found: %s", path)
        return []
    rows: list[dict] = []
    bad = 0
    with open(path, "r", encoding=encoding, errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return []
        # Strip BOM on first column.
        if header and header[0].startswith("﻿"):
            header[0] = header[0].lstrip("﻿")
        n = len(header)
        for row in reader:
            if len(row) != n:
                bad += 1
                continue
            rows.append(dict(zip(header, row)))
    if bad:
        logger.info("%s: skipped %d malformed rows", path.name, bad)
    return rows


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def _add_to_index(
    index: dict[str, list[tuple[int, float]]],
    field_text: str,
    row_idx: int,
    weight: float,
) -> None:
    """Tokenitza el camp i hi afegeix entrades (row_idx, weight) a l'índex."""
    if not field_text:
        return
    for tok in tokenize(normalize(field_text)):
        index[tok].append((row_idx, weight))


# ---------------------------------------------------------------------------
# Searcher
# ---------------------------------------------------------------------------

class Searcher:
    """
    Búsqueda unificada per al cercador instantani. Una sola instància es
    carrega un cop per procés via `get_searcher()`.
    """

    def __init__(self):
        self.cancons:  list[dict] = []
        self.grups:    list[dict] = []
        self.noticies: list[dict] = []

        # Inverted indexes: token -> list of (row_idx, weight)
        self._idx_cancons:  dict[str, list[tuple[int, float]]] = defaultdict(list)
        self._idx_grups:    dict[str, list[tuple[int, float]]] = defaultdict(list)
        self._idx_noticies: dict[str, list[tuple[int, float]]] = defaultdict(list)

        # Pre-normalitzat per als matches de substring (prefixos curts).
        self._cancons_norm:  list[str] = []   # title + " " + artist
        self._grups_norm:    list[str] = []   # name
        self._noticies_norm: list[str] = []   # title + " " + snippet

        self.parser = Parser2()
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        if self._loaded:
            return
        t0 = time.time()
        self._load_grups()
        self._load_noticies()
        self._load_cancons()
        self._load_parser()
        self._loaded = True
        logger.info("[searcher] ready in %.1fs (%d cançons, %d grups, %d notícies)",
                    time.time() - t0, len(self.cancons), len(self.grups), len(self.noticies))

    def _load_grups(self) -> None:
        for raw in _read_csv(_GRUPS):
            entry = {
                "id":           int(raw["id_grup"]) if raw.get("id_grup", "").isdigit() else 0,
                "name":         _safe(raw.get("nom")),
                "song_count":   int(raw["num_cancons"]) if raw.get("num_cancons", "").isdigit() else 0,
                "viasona_link": _safe(raw.get("viasona_link")),
                "foto":         _safe(raw.get("foto")),
                "municipi":     _safe(raw.get("municipi")),
                "regio":        _safe(raw.get("regio")),
                "genres":       [],
            }
            if not entry["name"]:
                continue
            row_idx = len(self.grups)
            self.grups.append(entry)
            _add_to_index(self._idx_grups, entry["name"], row_idx, _W_NAME)
            _add_to_index(self._idx_grups, _safe(raw.get("descripcio")), row_idx, _W_BODY)
            self._grups_norm.append(_fold(entry["name"]))

        # Ordenació estable per nom — desempata resultats amb mateixa puntuació.
        order = sorted(range(len(self.grups)), key=lambda i: self.grups[i]["name"].lower())
        self.grups = [self.grups[i] for i in order]
        self._grups_norm = [self._grups_norm[i] for i in order]
        # Reconstruir índex amb els nous row_idx (cost baix, 7K entrades).
        new_idx: dict[str, list[tuple[int, float]]] = defaultdict(list)
        old_to_new = {old: new for new, old in enumerate(order)}
        for tok, entries in self._idx_grups.items():
            for old_idx, w in entries:
                new_idx[tok].append((old_to_new[old_idx], w))
        self._idx_grups = new_idx

    def _load_noticies(self) -> None:
        for raw in _read_csv(_NOTICIES):
            snippet = _safe(raw.get("entrada")) or _safe(raw.get("subtitol"))
            entry = {
                "id":           int(raw["id_article"]) if raw.get("id_article", "").isdigit() else 0,
                "title":        _safe(raw.get("titol")),
                "date":         _safe(raw.get("data"))[:10],
                "snippet":      snippet[:250],
                "viasona_link": _safe(raw.get("viasona_link")),
            }
            if not entry["title"]:
                continue
            row_idx = len(self.noticies)
            self.noticies.append(entry)
            _add_to_index(self._idx_noticies, entry["title"], row_idx, _W_TITLE)
            _add_to_index(self._idx_noticies, _safe(raw.get("subtitol")), row_idx, _W_BODY)
            _add_to_index(self._idx_noticies, snippet, row_idx, _W_BODY)
            self._noticies_norm.append(_fold(entry["title"] + " " + entry["snippet"]))

    def _load_cancons(self) -> None:
        for raw in _read_csv(_CANCONS):
            id_str = raw.get("id_lletra", "")
            if not id_str.isdigit():
                continue
            title  = _safe(raw.get("titol"))
            artist = _safe(raw.get("artista"))
            if not title and not artist:
                continue
            lyrics = _safe(raw.get("lletra"))
            entry = {
                "id":             int(id_str),
                "title":          title,
                "artist":         artist,
                "album":          _safe(raw.get("album")),
                "lyrics_snippet": lyrics[:250],
                "full_lyrics":    lyrics,
                "url":            _safe(raw.get("viasona_link")),
                "duration":       _safe(raw.get("durada")),
                "genre":          "",
            }
            row_idx = len(self.cancons)
            self.cancons.append(entry)
            _add_to_index(self._idx_cancons, title,  row_idx, _W_TITLE)
            _add_to_index(self._idx_cancons, artist, row_idx, _W_ARTIST)
            # NOTA: NO indexem la lletra completa. Paraules funcionals
            # ("per", "tu", "no") apareixen a desenes de milers de cançons
            # i quan el parser2 expandeix la consulta a ~20 candidats
            # l'agregació explota (4-7 s per consulta). La cerca per
            # contingut de lletra és una altra funcionalitat — la cobreix
            # millor la cerca semàntica via embeddings.
            self._cancons_norm.append(_fold(title + " " + artist))

    def _load_parser(self) -> None:
        # Cataleg per al phrase-match: títol + artista de cada cançó +
        # nom de cada grup. Notícies queden fora (els "títols" de notícies
        # són frases llargues que enbruten el phrase-match del parser).
        catalog = [{"title": s["title"], "artist": s["artist"]} for s in self.cancons]
        for g in self.grups:
            catalog.append({"title": g["name"], "artist": ""})
        self.parser.load_catalog(catalog)
        try:
            self.parser.load_lexicon(min_zipf=2.4)
        except Exception as exc:
            logger.warning("Could not load lexicon (%s); fuzzy lexicon path disabled", exc)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> dict:
        if not self._loaded:
            self.load()

        q = query.strip()
        if not q:
            return {"grups": [], "cancons": [], "noticies": [], "correction": None}

        # 1. Expandir la query a un bag-of-words { paraula: prob }.
        parsed = self.parser.parse(q)
        if not parsed:
            return {"grups": [], "cancons": [], "noticies": [], "correction": None}

        # 2. Substring fold per cada query — ajuda amb prefixos curts ("bo")
        #    on el parser potser no genera el token complet. Només l'aplico
        #    a camps curts (nom/títol) per cost.
        q_fold = _fold(normalize(q))

        # 3. Score per dataset.
        grups_top    = self._rank(self._idx_grups,    self._grups_norm,    parsed, q_fold, top_k=5)
        cancons_top  = self._rank(self._idx_cancons,  self._cancons_norm,  parsed, q_fold, top_k=8)
        noticies_top = self._rank(self._idx_noticies, self._noticies_norm, parsed, q_fold, top_k=5)

        # 4. Correcció ("Volies dir") — paraula amb la prob més alta que
        #    NO sigui un dels tokens de la consulta original.
        correction = self._build_correction(q, parsed)

        return {
            "grups":      [self.grups[i]    for i, _ in grups_top],
            "cancons":    [self.cancons[i]  for i, _ in cancons_top],
            "noticies":   [self.noticies[i] for i, _ in noticies_top],
            "correction": correction,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _rank(
        self,
        index: dict[str, list[tuple[int, float]]],
        norm_fields: list[str],
        parsed: dict[str, float],
        q_fold: str,
        top_k: int,
    ) -> list[tuple[int, float]]:
        """
        Suma probabilitats × pes-de-camp per cada row_idx que apareix a
        l'índex per qualsevol de les paraules expandides. Afegeix bonus
        si la query normalitzada (substring) cau dins el camp curt
        pre-foldat — això cobreix prefixos del tipus "bo" → "boig".
        """
        scores: dict[int, float] = defaultdict(float)
        for word, prob in parsed.items():
            entries = index.get(word)
            if not entries:
                continue
            for row_idx, weight in entries:
                scores[row_idx] += prob * weight

        # Substring boost (només si la query té ≥2 caràcters i no és pura puntuació).
        if len(q_fold) >= 2:
            for row_idx, hay in enumerate(norm_fields):
                if q_fold in hay:
                    scores[row_idx] += 1.5  # exact-substring és senyal forta

        if not scores:
            return []
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return ranked[:top_k]

    def _build_correction(self, original: str, parsed: dict[str, float]) -> dict | None:
        """
        Si l'usuari ha escrit malament i el parser ha trobat un candidat
        prou fort que NO és cap dels tokens originals, retorna-ho com a
        suggeriment. Si no, None.
        """
        original_tokens = set(tokenize(normalize(original)))
        # Items ja estan ordenats per prob descendent (parser.parse ho fa).
        candidates = [
            (w, p) for w, p in parsed.items()
            if w not in original_tokens and p >= _CORRECTION_PROB
        ]
        if not candidates:
            return None

        # Substituir cada token de la query original pel millor candidat
        # més proper (per edit-distance simple) — així obtenim una versió
        # "corregida" llegible per l'usuari.
        best = candidates[0][0]
        suggestions = [w for w, _ in candidates[1:4]]
        return {
            "corrected":   best,
            "suggestions": suggestions,
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_singleton: Searcher | None = None


def get_searcher() -> Searcher:
    global _singleton
    if _singleton is None:
        _singleton = Searcher()
        _singleton.load()
    return _singleton
