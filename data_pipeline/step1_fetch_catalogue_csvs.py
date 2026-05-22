"""
Step 1 — fetch the three catalogue CSVs (cancons.csv, grups.csv, noticies.csv)
from the Viasona MariaDB instance.

Behaviour:

* If the three CSVs already exist on disk, this step is a no-op (logs and
  returns).  Use ``--force`` to refetch.
* Otherwise, attempt to connect using ``.env`` credentials.  On success,
  query the DB and write the three CSVs.
* On DB-connection failure (missing credentials, unreachable host, etc.),
  warn the user — but only refuse to continue if a required CSV is missing
  from disk *and* could not be fetched.

The SQL / cleaning logic is the same one previously in
``app/backend/core/data_getter.py``; this is the consolidated home for it.
"""

from __future__ import annotations

import argparse
import csv as _csv
import html
import logging
import os
import re
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

from ._paths import CANCONS_CSV, ENV_FILE, GRUPS_CSV, NOTICIES_CSV

logger = logging.getLogger(__name__)

VIASONA_BASE_URL = "https://www.viasona.cat"


# ── Helpers ─────────────────────────────────────────────────────────────────

def _clean_html(value) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)<div[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_url(value) -> str:
    if value is None:
        return ""
    v = str(value).strip()
    if not v:
        return ""
    if v.startswith(("http://", "https://")):
        return v
    return "https://" + v


def _build_image_url(directori, fitxer) -> str:
    if not directori or not fitxer:
        return ""
    return f"{VIASONA_BASE_URL}/{str(directori).strip().strip('/')}/{str(fitxer).strip().strip('/')}"


def _build_song_link(uri_grup, uri_album, uri_canco) -> str:
    """Build the public Viasona song URL.

    Viasona routes songs under the artist (not under ``/lletra/{id}/``):
      * with album:    ``/grup/{artist-uri}/{album-uri}/{song-uri}``
      * without album: ``/grup/{artist-uri}/{song-uri}``
    Any artist slug linked to the song works (collabs accept any of them).
    """
    artist = str(uri_grup or "").strip().strip("/")
    song   = str(uri_canco or "").strip().strip("/")
    album  = str(uri_album or "").strip().strip("/")
    if not artist or not song:
        return ""
    if album:
        return f"{VIASONA_BASE_URL}/grup/{artist}/{album}/{song}"
    return f"{VIASONA_BASE_URL}/grup/{artist}/{song}"


def _build_group_link(uri) -> str:
    """Build the public Viasona artist URL: ``/grup/{artist-uri}`` (no id)."""
    u = str(uri or "").strip().strip("/")
    if not u:
        return ""
    return f"{VIASONA_BASE_URL}/grup/{u}"


def _join_unique(values) -> str:
    out: list[str] = []
    for v in values:
        if v is None:
            continue
        v = str(v).strip()
        if v and v not in out:
            out.append(v)
    return " | ".join(out)


def _first_non_empty(values) -> str:
    for v in values:
        if v is None:
            continue
        v = str(v).strip()
        if v:
            return v
    return ""


def _save(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ── DB extraction ───────────────────────────────────────────────────────────

_NEWS_SQL = """
    SELECT
        a.id_article, a.titol, a.subtitol, a.entrada, a.contingut, a.data, a.uri,
        GROUP_CONCAT(DISTINCT au.nom ORDER BY au.nom SEPARATOR ', ')      AS autors,
        GROUP_CONCAT(DISTINCT c.titol ORDER BY c.titol SEPARATOR ', ')     AS categories
    FROM articles a
    LEFT JOIN articles_autors aa     ON aa.id_article = a.id_article
    LEFT JOIN autors au              ON au.id_autor   = aa.id_autor
    LEFT JOIN articles_categories ac ON ac.id_article = a.id_article
    LEFT JOIN categories c           ON c.id_categoria = ac.id_categoria
    WHERE a.tipus = 'noticia' AND a.estat = 'actiu'
    GROUP BY a.id_article, a.titol, a.subtitol, a.entrada, a.contingut, a.data, a.uri
    ORDER BY a.data DESC;
"""

_GROUPS_SQL = """
    SELECT g.id_grup, g.titol, g.uri, g.contingut,
        g.web, g.blog, g.wikipedia, g.myspace, g.twitter, g.facebook, g.youtube,
        g.bandcamp, g.soundcloud, g.instagram, g.bluesky, g.musicalliure, g.tiktok,
        g.municipi, g.regio,
        img.titol AS imatge_titol, img.autor AS imatge_autor,
        img.autor_url AS imatge_autor_url, img.enllac AS imatge_enllac,
        img.directori AS imatge_directori, img.fitxer AS imatge_fitxer,
        sp.spotify AS spotify, dz.id_deezer AS id_deezer,
        (SELECT COUNT(*) FROM grups_discos gd
            WHERE gd.id_grup_vell = g.id_grup AND gd.estat = 'actiu') AS num_albums,
        (SELECT COUNT(*) FROM grups_lletres gl
            WHERE gl.id_grup_vell = g.id_grup AND gl.estat = 'actiu'
              AND gl.tipus = 'lletra' AND gl.oculta = 'false') AS num_cancons,
        (SELECT GROUP_CONCAT(DISTINCT gr2.titol ORDER BY gr.ordre SEPARATOR ', ')
            FROM grups_relacionats gr
            JOIN grups gr2 ON gr2.id_grup = gr.id_grup_relacionat
            WHERE gr.id_grup = g.id_grup AND gr2.estat = 'actiu') AS grups_relacionats
    FROM grups g
    LEFT JOIN grups_imatges gi ON gi.id_grup = g.id_grup
        AND gi.ordre = (SELECT MIN(gi2.ordre) FROM grups_imatges gi2
                            WHERE gi2.id_grup = g.id_grup)
    LEFT JOIN imatges img ON img.id_imatge = gi.id_imatge
    LEFT JOIN grups_spotify sp ON sp.id_element = g.id_grup
        AND sp.tipus = 'grup' AND sp.trobat = 'true'
    LEFT JOIN grups_deezer  dz ON dz.id_element = g.id_grup
        AND dz.tipus = 'grup' AND dz.trobat = 'true'
    WHERE g.estat = 'actiu'
    GROUP BY g.id_grup, g.titol, g.uri, g.contingut, g.web, g.blog, g.wikipedia,
             g.myspace, g.twitter, g.facebook, g.youtube, g.bandcamp, g.soundcloud,
             g.instagram, g.bluesky, g.musicalliure, g.tiktok, g.municipi, g.regio,
             img.titol, img.autor, img.autor_url, img.enllac, img.directori,
             img.fitxer, sp.spotify, dz.id_deezer
    ORDER BY g.titol ASC;
"""

_SONGS_SQL = """
    SELECT gl.id_lletra, gl.titol AS titol_canco, gl.uri AS uri_canco,
        gl.contingut AS lletra, gl.autor, gl.compositor, gl.temps, gl.data,
        COALESCE(g_rel.titol,  g_directe.titol)   AS nom_grup,
        COALESCE(g_rel.uri,    g_directe.uri)     AS uri_grup,
        COALESCE(gd_rel.titol, gd_directe.titol)  AS titol_album,
        COALESCE(gd_rel.uri,   gd_directe.uri)    AS uri_album
    FROM grups_lletres gl
    LEFT JOIN grups_lletres_rel glr ON gl.id_lletra = glr.id_lletra
    LEFT JOIN grups g_rel         ON glr.id_grup = g_rel.id_grup
    LEFT JOIN grups g_directe     ON gl.id_grup_vell = g_directe.id_grup
    LEFT JOIN grups_discos_lletres_rel gdlr ON gl.id_lletra = gdlr.id_lletra
    LEFT JOIN grups_discos gd_rel      ON gdlr.id_disc = gd_rel.id_disc
    LEFT JOIN grups_discos gd_directe  ON gl.id_disc_vell = gd_directe.id_disc
    WHERE gl.estat = 'actiu' AND gl.tipus = 'lletra' AND gl.oculta = 'false'
      AND gl.contingut IS NOT NULL AND gl.contingut <> ''
"""


def _news_rows(cursor) -> list[dict]:
    cursor.execute(_NEWS_SQL)
    out = []
    for r in cursor.fetchall():
        out.append({
            "id_article":  r["id_article"],
            "titol":       _clean_html(r["titol"]),
            "subtitol":    _clean_html(r["subtitol"]),
            "entrada":     _clean_html(r["entrada"]),
            "text":        _clean_html(r["contingut"]),
            "data":        r["data"],
            "autor":       _clean_html(r["autors"]),
            "categories":  _clean_html(r["categories"]),
            "viasona_link": f"{VIASONA_BASE_URL}/noticia/{r['id_article']}/{r['uri']}",
        })
    return out


def _groups_rows(cursor) -> list[dict]:
    cursor.execute(_GROUPS_SQL)
    out = []
    for r in cursor.fetchall():
        twitter   = str(r["twitter"]   or "").strip()
        instagram = str(r["instagram"] or "").strip()
        tiktok    = str(r["tiktok"]    or "").strip()
        spotify   = str(r["spotify"]   or "").strip()
        id_deezer = str(r["id_deezer"] or "").strip()
        out.append({
            "id_grup":          r["id_grup"],
            "nom":              _clean_html(r["titol"]),
            "descripcio":       _clean_html(r["contingut"]),
            "foto":             _build_image_url(r["imatge_directori"], r["imatge_fitxer"]),
            "foto_titol":       _clean_html(r["imatge_titol"]),
            "foto_autor":       _clean_html(r["imatge_autor"]),
            "foto_autor_url":   _clean_url(r["imatge_autor_url"]),
            "foto_enllac":      _clean_url(r["imatge_enllac"]),
            "municipi":         _clean_html(r["municipi"]),
            "regio":            _clean_html(r["regio"]),
            "web":              _clean_url(r["web"]),
            "blog":             _clean_url(r["blog"]),
            "wikipedia":        _clean_url(r["wikipedia"]),
            "myspace":          _clean_url(r["myspace"]),
            "facebook":         _clean_url(r["facebook"]),
            "youtube":          _clean_url(r["youtube"]),
            "bandcamp":         _clean_url(r["bandcamp"]),
            "soundcloud":       _clean_url(r["soundcloud"]),
            "musicalliure":     _clean_url(r["musicalliure"]),
            "twitter":   (f"https://twitter.com/{twitter.lstrip('@')}"        if twitter   and not twitter.startswith("http")   else _clean_url(twitter)),
            "instagram": (f"https://www.instagram.com/{instagram.lstrip('@')}" if instagram and not instagram.startswith("http") else _clean_url(instagram)),
            "tiktok":    (f"https://www.tiktok.com/@{tiktok.lstrip('@')}"      if tiktok    and not tiktok.startswith("http")    else _clean_url(tiktok)),
            "spotify":   (f"https://open.spotify.com/artist/{spotify}"          if spotify   and not spotify.startswith("http")   else _clean_url(spotify)),
            "deezer":    f"https://www.deezer.com/artist/{id_deezer}" if id_deezer else "",
            "num_albums":        r["num_albums"],
            "num_cancons":       r["num_cancons"],
            "grups_relacionats": _clean_html(r["grups_relacionats"]),
            "viasona_link":      _build_group_link(r["uri"]),
        })
    return out


def _songs_rows(cursor) -> list[dict]:
    cursor.execute(_SONGS_SQL)
    rows = cursor.fetchall()
    if not rows:
        return []

    df = pd.DataFrame(rows)
    for col in ("nom_grup", "titol_canco", "titol_album", "lletra", "autor", "compositor"):
        df[col] = df[col].apply(_clean_html)
    df["uri_canco"] = df["uri_canco"].fillna("").astype(str)
    df["uri_grup"]  = df["uri_grup"].fillna("").astype(str)
    df["uri_album"] = df["uri_album"].fillna("").astype(str)
    df = df[df["lletra"].str.strip() != ""]

    grouped = (df.groupby(["nom_grup", "lletra", "titol_canco"], dropna=False, as_index=False)
                 .agg({
                     "titol_album": _join_unique,
                     "id_lletra":   "min",
                     "uri_canco":   _first_non_empty,
                     "uri_grup":    _first_non_empty,
                     "uri_album":   _first_non_empty,
                     "autor":       _join_unique,
                     "compositor":  _join_unique,
                     "temps":       _first_non_empty,
                     "data":        _first_non_empty,
                 }))

    titles_with_artist = set(
        grouped.loc[grouped["nom_grup"].notna() & (grouped["nom_grup"] != ""), "titol_canco"]
    )
    drop_mask = (grouped["nom_grup"].isna() | (grouped["nom_grup"] == "")) \
                & grouped["titol_canco"].isin(titles_with_artist)
    grouped = grouped[~drop_mask].copy()
    grouped = grouped.rename(columns={
        "nom_grup": "artista", "titol_canco": "titol", "titol_album": "album",
    })

    out = []
    for _, row in grouped.iterrows():
        id_lletra = row["id_lletra"]
        out.append({
            "id_lletra":    int(id_lletra) if pd.notna(id_lletra) else "",
            "artista":      row["artista"]    if pd.notna(row["artista"])    else "",
            "titol":        row["titol"]      if pd.notna(row["titol"])      else "",
            "album":        row["album"]      if pd.notna(row["album"])      else "",
            "lletra":       row["lletra"]     if pd.notna(row["lletra"])     else "",
            "autor":        row["autor"]      if pd.notna(row["autor"])      else "",
            "compositor":   row["compositor"] if pd.notna(row["compositor"]) else "",
            "durada":       str(row["temps"]) if pd.notna(row["temps"]) else "",
            "data":         str(row["data"])  if pd.notna(row["data"])  else "",
            "viasona_link": _build_song_link(row["uri_grup"], row["uri_album"], row["uri_canco"]),
        })
    return out


def _db_config() -> dict | None:
    load_dotenv(ENV_FILE)
    required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.warning("DB credentials missing from %s (vars %s).", ENV_FILE, missing)
        return None
    return {
        "host":     os.getenv("DB_HOST"),
        "port":     int(os.getenv("DB_PORT") or 3306),
        "user":     os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
    }


def _fetch_from_db(cfg: dict) -> dict:
    logger.info("Connecting to %s:%s …", cfg["host"], cfg["port"])
    conn = pymysql.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], database=cfg["database"],
        charset="utf8mb4", cursorclass=DictCursor, connect_timeout=15,
    )
    try:
        with conn.cursor() as cur:
            news   = _news_rows(cur);   logger.info("news rows: %d",   len(news))
            groups = _groups_rows(cur); logger.info("groups rows: %d", len(groups))
            songs  = _songs_rows(cur);  logger.info("songs rows: %d",  len(songs))
    finally:
        conn.close()

    _save(news,   NOTICIES_CSV)
    _save(groups, GRUPS_CSV)
    _save(songs,  CANCONS_CSV)
    return {"news": len(news), "groups": len(groups), "songs": len(songs)}


def run(force: bool = False) -> dict:
    """Materialise cancons/grups/noticies.csv. Skips if all three already exist."""
    targets = [NOTICIES_CSV, GRUPS_CSV, CANCONS_CSV]
    have_all = all(p.exists() and p.stat().st_size > 0 for p in targets)
    if have_all and not force:
        logger.info("Catalogue CSVs already present — skipping DB fetch. Use --force to refresh.")
        return {"skipped": True, "files": [str(p) for p in targets]}

    cfg = _db_config()
    if cfg is None:
        # Couldn't get credentials. Tolerate if files already exist.
        if have_all:
            logger.warning("Falling back to existing CSVs on disk.")
            return {"skipped": True, "fallback": True}
        missing = [p.name for p in targets if not p.exists()]
        raise RuntimeError(
            f"Cannot fetch catalogue from DB (no credentials in {ENV_FILE}) "
            f"and these files are missing: {missing}."
        )

    try:
        return _fetch_from_db(cfg)
    except pymysql.MySQLError as exc:
        if have_all:
            logger.warning("DB fetch failed (%s) — keeping existing CSVs on disk.", exc)
            return {"skipped": True, "fallback": True, "error": str(exc)}
        missing = [p.name for p in targets if not p.exists()]
        raise RuntimeError(
            f"DB fetch failed ({exc}) and these files are missing: {missing}."
        ) from exc


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true",
                   help="Refetch even if the three CSVs already exist on disk.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run(force=args.force)
    print(result)


if __name__ == "__main__":
    main()
