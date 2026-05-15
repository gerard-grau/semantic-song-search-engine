"""
Build ``app/backend/data/songs_meta.parquet`` by fetching song metadata
straight from the ``viasona`` database for the ids contained in
``embedded_songs_top5000.parquet``.

Why this exists:
    ``data_pipeline.run_metadata_snapshot()`` builds the same artefact, but
    by streaming ``augmented_songs.csv`` + ``cancons.csv``. When those CSVs
    aren't present, this script gets the data straight from MariaDB.

Output schema matches what ``app/backend/core/data_loader._read_meta_snapshot``
expects: ``id, title, artist, album, genre, year, lyrics_snippet,
full_lyrics, url, duration, language`` (+ ``embedding`` filled in lazily).

Usage:
    python3 -m etl.build_songs_meta_from_db
    python3 -m etl.build_songs_meta_from_db --ids-parquet path/to/embedded_songs_top5000.parquet
"""

from __future__ import annotations

import argparse
import html
import logging
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pymysql

logger = logging.getLogger(__name__)

_REPO_ROOT       = Path(__file__).resolve().parent.parent
_DATA_DIR        = _REPO_ROOT / "app" / "backend" / "data"
_IDS_PARQUET     = _DATA_DIR / "embedded_songs_top5000.parquet"
_OUTPUT_PARQUET  = _DATA_DIR / "songs_meta.parquet"

DB_HOST     = "aulagpus.fib.upc.edu"
DB_PORT     = 60059
DB_USER     = "pe"
DB_PASSWORD = "bernatpudent"
DB_NAME     = "viasona"

# Viasona song URL pattern: https://www.viasona.cat/grup/{artist}/{album}/{song}
_VIASONA_BASE = "https://www.viasona.cat/grup"


def _read_top_pairs(path: Path) -> list[tuple[int, str]]:
    """Return ``(id_lyrics, artist)`` pairs in popularity order.

    The enriched top-5000 parquet stores both columns so multi-artist
    songs (same id_lyrics, different artists) don't collide.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `python -m etl.merge_top5000_with_db` first."
        )
    table = pq.read_table(path, columns=["id_lyrics", "artist"]).to_pandas()
    return [(int(i), str(a) if a is not None else "")
            for i, a in zip(table["id_lyrics"], table["artist"])]


def _strip_html(s: str | None) -> str:
    """Lyrics in ``grups_lletres.contingut`` are stored with ``<br />`` and
    other HTML entities. Strip them to plain text for the popup display."""
    if not s:
        return ""
    text = re.sub(r"<\s*br\s*/?>", "\n", str(s), flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.strip()


def _format_duration(temps) -> str:
    """``grups_lletres.temps`` is a TIME column; pymysql returns ``timedelta``.

    Convert to ``M:SS`` (or ``H:MM:SS`` for >1h). Zero/blank → empty string."""
    if temps is None:
        return ""
    total = int(getattr(temps, "total_seconds", lambda: 0)()) if hasattr(temps, "total_seconds") else 0
    if total <= 0:
        # Fall back to string parsing in case pymysql returned a str.
        s = str(temps).strip()
        if not s or s in ("00:00:00", "0:00:00"):
            return ""
        return s
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _norm_key(s: str) -> str:
    import unicodedata as _ud
    text = _ud.normalize("NFKD", str(s or ""))
    text = "".join(c for c in text if not _ud.combining(c))
    return re.sub(r"\s+", " ", text.lower().strip())


def fetch_metadata(pairs: list[tuple[int, str]]) -> list[dict]:
    """Return one dict per ``(id_lyrics, artist)`` pair.

    The artist comes from the top-5000 parquet (which got it from
    augmented_songs.csv); the DB supplies title/album/year/duration/lyrics/
    URL slugs. For multi-artist songs we resolve the matching grup row by
    name so the constructed URL uses the right artist slug.
    """
    if not pairs:
        return []

    ids = sorted({pid for pid, _ in pairs})
    placeholders = ",".join(["%s"] * len(ids))
    # Per-song fields (title/lyrics/duration/year/album/URL parts).
    song_query = f"""
        SELECT
            gl.id_lletra        AS id,
            gl.titol            AS title,
            gl.uri              AS song_uri,
            gl.contingut        AS lyrics,
            gl.temps            AS duration,
            gl.altra_llengua    AS other_language,
            d.titol             AS album,
            d.uri               AS album_uri,
            d.any               AS year
        FROM grups_lletres gl
        LEFT JOIN (
            SELECT gdlr.id_lletra, MIN(gdlr.id_disc) AS id_disc
            FROM grups_discos_lletres_rel gdlr
            GROUP BY gdlr.id_lletra
        ) gdlr1 ON gdlr1.id_lletra = gl.id_lletra
        LEFT JOIN grups_discos d ON d.id_disc = gdlr1.id_disc
        WHERE gl.id_lletra IN ({placeholders})
    """
    # All artists linked to each lletra — used to pick the right artist
    # slug for URL construction.
    artist_query = f"""
        SELECT glr.id_lletra AS id, g.titol AS artist, g.uri AS artist_uri
        FROM grups_lletres_rel glr
        JOIN grups g ON g.id_grup = glr.id_grup
        WHERE glr.id_lletra IN ({placeholders})
    """

    logger.info("Querying viasona for %d song ids …", len(ids))
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, connect_timeout=15, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(song_query, ids)
            song_rows = cur.fetchall()
            cur.execute(artist_query, ids)
            artist_rows = cur.fetchall()
    finally:
        conn.close()
    logger.info("DB returned %d song rows, %d artist links.",
                len(song_rows), len(artist_rows))

    # id_lyrics → {norm(artist_name) → artist_uri}
    artists_by_id: dict[int, dict[str, str]] = {}
    for r in artist_rows:
        sid = int(r["id"])
        artists_by_id.setdefault(sid, {})[_norm_key(r["artist"])] = (r["artist_uri"] or "")

    by_id: dict[int, dict] = {}
    for r in song_rows:
        sid = int(r["id"])
        if sid in by_id:
            continue
        lyrics_text = _strip_html(r.get("lyrics"))
        year_val = r.get("year")
        try:
            year_int = int(year_val) if year_val else 0
        except (TypeError, ValueError):
            year_int = 0
        by_id[sid] = {
            "title":          (r.get("title") or "").strip(),
            "song_uri":       (r.get("song_uri") or "").strip(),
            "album":          (r.get("album") or "").strip(),
            "album_uri":      (r.get("album_uri") or "").strip(),
            "year":           year_int,
            "duration":       _format_duration(r.get("duration")),
            "language":       "Català" if (r.get("other_language") != "true") else "Altres",
            "lyrics_snippet": lyrics_text[:300].strip(),
            "full_lyrics":    lyrics_text,
        }

    songs: list[dict] = []
    missing = 0
    for sid, artist in pairs:
        rec = by_id.get(int(sid))
        if rec is None:
            missing += 1
            continue
        artist_map = artists_by_id.get(int(sid), {})
        # Prefer the exact artist slug; fall back to any one if absent.
        artist_uri = artist_map.get(_norm_key(artist))
        if not artist_uri and artist_map:
            artist_uri = next(iter(artist_map.values()))

        url = ""
        if artist_uri and rec["song_uri"]:
            url = (f"{_VIASONA_BASE}/{artist_uri}/{rec['album_uri']}/{rec['song_uri']}"
                   if rec["album_uri"]
                   else f"{_VIASONA_BASE}/{artist_uri}/{rec['song_uri']}")

        songs.append({
            "id":             int(sid),
            "title":          rec["title"],
            "artist":         artist,
            "album":          rec["album"],
            "genre":          "",
            "year":           rec["year"],
            "lyrics_snippet": rec["lyrics_snippet"],
            "full_lyrics":    rec["full_lyrics"],
            "url":            url,
            "duration":       rec["duration"],
            "language":       rec["language"],
        })
    if missing:
        logger.warning("%d ids had no DB row (active filter or stale id).", missing)
    return songs


def main() -> None:
    p = argparse.ArgumentParser(description="Build songs_meta.parquet from viasona.")
    p.add_argument("--ids-parquet", type=Path, default=_IDS_PARQUET)
    p.add_argument("--output", type=Path, default=_OUTPUT_PARQUET)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    pairs = _read_top_pairs(args.ids_parquet)
    logger.info("Read %d (id, artist) pairs from %s", len(pairs), args.ids_parquet)
    songs = fetch_metadata(pairs)
    if not songs:
        raise RuntimeError("No metadata rows produced — refusing to write empty parquet.")

    df = pd.DataFrame(songs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    df.to_parquet(args.output, index=False)
    print(f"Done: {len(df)} rows → {args.output}")


if __name__ == "__main__":
    main()
