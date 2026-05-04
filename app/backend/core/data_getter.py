import csv
import re
import html
import os
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor


VIASONA_BASE_URL = "https://www.viasona.cat"


# ---------------------------------------------------------------------
# NETEJA I FORMAT
# ---------------------------------------------------------------------

def clean_html(value):
    """
    Converteix HTML en text net.
    Manté una mica d'estructura de paràgrafs.
    """
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


def clean_url(value):
    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        return value

    return "https://" + value


def build_image_url(directori, fitxer):
    """
    Construeix una URL probable de la imatge de grup.

    Si la ruta real de Viasona fos diferent, només cal canviar aquesta funció.
    """
    if not directori or not fitxer:
        return ""

    directori = str(directori).strip().strip("/")
    fitxer = str(fitxer).strip().strip("/")

    return f"{VIASONA_BASE_URL}/{directori}/{fitxer}"


def build_song_link(id_lletra, uri):
    if not id_lletra or not uri:
        return ""

    return f"{VIASONA_BASE_URL}/lletra/{id_lletra}/{uri}"


def save_info(rows, path):
    """
    Guarda una llista de diccionaris en CSV.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            pass
        return

    fieldnames = list(rows[0].keys())

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def join_unique(values):
    """
    Uneix valors únics no buits amb ' | '.
    """
    clean_values = []

    for value in values:
        if value is None:
            continue

        value = str(value).strip()

        if value and value not in clean_values:
            clean_values.append(value)

    return " | ".join(clean_values)


def first_non_empty(values):
    """
    Retorna el primer valor no buit.
    """
    for value in values:
        if value is None:
            continue

        value = str(value).strip()

        if value:
            return value

    return ""


# ---------------------------------------------------------------------
# NOTÍCIES
# ---------------------------------------------------------------------

def get_news_info(cursor):
    """
    Exporta només informació útil per recrear una notícia:

    - id_article
    - titol
    - subtitol
    - entrada
    - text
    - data
    - autor
    - categories
    - link intern de Viasona

    No exporta imatges.
    """

    sql = """
        SELECT
            a.id_article,
            a.titol,
            a.subtitol,
            a.entrada,
            a.contingut,
            a.data,
            a.uri,
            GROUP_CONCAT(DISTINCT au.nom ORDER BY au.nom SEPARATOR ', ') AS autors,
            GROUP_CONCAT(DISTINCT c.titol ORDER BY c.titol SEPARATOR ', ') AS categories
        FROM articles a
        LEFT JOIN articles_autors aa
            ON aa.id_article = a.id_article
        LEFT JOIN autors au
            ON au.id_autor = aa.id_autor
        LEFT JOIN articles_categories ac
            ON ac.id_article = a.id_article
        LEFT JOIN categories c
            ON c.id_categoria = ac.id_categoria
        WHERE a.tipus = 'noticia'
          AND a.estat = 'actiu'
        GROUP BY
            a.id_article,
            a.titol,
            a.subtitol,
            a.entrada,
            a.contingut,
            a.data,
            a.uri
        ORDER BY a.data DESC;
    """

    cursor.execute(sql)
    rows = cursor.fetchall()

    result = []

    for row in rows:
        viasona_link = f"{VIASONA_BASE_URL}/noticia/{row['id_article']}/{row['uri']}"

        item = {
            "id_article": row["id_article"],
            "titol": clean_html(row["titol"]),
            "subtitol": clean_html(row["subtitol"]),
            "entrada": clean_html(row["entrada"]),
            "text": clean_html(row["contingut"]),
            "data": row["data"],
            "autor": clean_html(row["autors"]),
            "categories": clean_html(row["categories"]),
            "viasona_link": viasona_link,
        }

        result.append(item)

    return result


# ---------------------------------------------------------------------
# GRUPS
# ---------------------------------------------------------------------

def get_groups_info(cursor):
    """
    Exporta informació útil per recrear una fitxa de grup:

    - nom
    - descripcio
    - foto
    - municipi
    - regio
    - web
    - xarxes
    - num_albums
    - num_cancons
    - relacionats
    - link intern de Viasona
    """

    sql = """
        SELECT
            g.id_grup,
            g.titol,
            g.uri,
            g.contingut,
            g.web,
            g.blog,
            g.wikipedia,
            g.myspace,
            g.twitter,
            g.facebook,
            g.youtube,
            g.bandcamp,
            g.soundcloud,
            g.instagram,
            g.bluesky,
            g.musicalliure,
            g.tiktok,
            g.municipi,
            g.regio,

            img.titol AS imatge_titol,
            img.autor AS imatge_autor,
            img.autor_url AS imatge_autor_url,
            img.enllac AS imatge_enllac,
            img.directori AS imatge_directori,
            img.fitxer AS imatge_fitxer,

            sp.spotify AS spotify,
            dz.id_deezer AS id_deezer,

            (
                SELECT COUNT(*)
                FROM grups_discos gd
                WHERE gd.id_grup_vell = g.id_grup
                  AND gd.estat = 'actiu'
            ) AS num_albums,

            (
                SELECT COUNT(*)
                FROM grups_lletres gl
                WHERE gl.id_grup_vell = g.id_grup
                  AND gl.estat = 'actiu'
                  AND gl.tipus = 'lletra'
                  AND gl.oculta = 'false'
            ) AS num_cancons,

            (
                SELECT GROUP_CONCAT(DISTINCT gr2.titol ORDER BY gr.ordre SEPARATOR ', ')
                FROM grups_relacionats gr
                JOIN grups gr2
                    ON gr2.id_grup = gr.id_grup_relacionat
                WHERE gr.id_grup = g.id_grup
                  AND gr2.estat = 'actiu'
            ) AS grups_relacionats

        FROM grups g

        LEFT JOIN grups_imatges gi
            ON gi.id_grup = g.id_grup
           AND gi.ordre = (
                SELECT MIN(gi2.ordre)
                FROM grups_imatges gi2
                WHERE gi2.id_grup = g.id_grup
           )

        LEFT JOIN imatges img
            ON img.id_imatge = gi.id_imatge

        LEFT JOIN grups_spotify sp
            ON sp.id_element = g.id_grup
           AND sp.tipus = 'grup'
           AND sp.trobat = 'true'

        LEFT JOIN grups_deezer dz
            ON dz.id_element = g.id_grup
           AND dz.tipus = 'grup'
           AND dz.trobat = 'true'

        WHERE g.estat = 'actiu'

        GROUP BY
            g.id_grup,
            g.titol,
            g.uri,
            g.contingut,
            g.web,
            g.blog,
            g.wikipedia,
            g.myspace,
            g.twitter,
            g.facebook,
            g.youtube,
            g.bandcamp,
            g.soundcloud,
            g.instagram,
            g.bluesky,
            g.musicalliure,
            g.tiktok,
            g.municipi,
            g.regio,
            img.titol,
            img.autor,
            img.autor_url,
            img.enllac,
            img.directori,
            img.fitxer,
            sp.spotify,
            dz.id_deezer

        ORDER BY g.titol ASC;
    """

    cursor.execute(sql)
    rows = cursor.fetchall()

    result = []

    for row in rows:
        viasona_link = f"{VIASONA_BASE_URL}/grup/{row['id_grup']}/{row['uri']}"

        twitter = str(row["twitter"]).strip() if row["twitter"] else ""
        instagram = str(row["instagram"]).strip() if row["instagram"] else ""
        tiktok = str(row["tiktok"]).strip() if row["tiktok"] else ""
        spotify = str(row["spotify"]).strip() if row["spotify"] else ""
        id_deezer = str(row["id_deezer"]).strip() if row["id_deezer"] else ""

        item = {
            "id_grup": row["id_grup"],
            "nom": clean_html(row["titol"]),
            "descripcio": clean_html(row["contingut"]),
            "foto": build_image_url(row["imatge_directori"], row["imatge_fitxer"]),
            "foto_titol": clean_html(row["imatge_titol"]),
            "foto_autor": clean_html(row["imatge_autor"]),
            "foto_autor_url": clean_url(row["imatge_autor_url"]),
            "foto_enllac": clean_url(row["imatge_enllac"]),
            "municipi": clean_html(row["municipi"]),
            "regio": clean_html(row["regio"]),
            "web": clean_url(row["web"]),
            "blog": clean_url(row["blog"]),
            "wikipedia": clean_url(row["wikipedia"]),
            "myspace": clean_url(row["myspace"]),
            "facebook": clean_url(row["facebook"]),
            "youtube": clean_url(row["youtube"]),
            "bandcamp": clean_url(row["bandcamp"]),
            "soundcloud": clean_url(row["soundcloud"]),
            "musicalliure": clean_url(row["musicalliure"]),
            "twitter": (
                f"https://twitter.com/{twitter.lstrip('@')}"
                if twitter and not twitter.startswith("http")
                else clean_url(twitter)
            ),
            "instagram": (
                f"https://www.instagram.com/{instagram.lstrip('@')}"
                if instagram and not instagram.startswith("http")
                else clean_url(instagram)
            ),
            "tiktok": (
                f"https://www.tiktok.com/@{tiktok.lstrip('@')}"
                if tiktok and not tiktok.startswith("http")
                else clean_url(tiktok)
            ),
            "spotify": (
                f"https://open.spotify.com/artist/{spotify}"
                if spotify and not spotify.startswith("http")
                else clean_url(spotify)
            ),
            "deezer": f"https://www.deezer.com/artist/{id_deezer}" if id_deezer else "",
            "num_albums": row["num_albums"],
            "num_cancons": row["num_cancons"],
            "grups_relacionats": clean_html(row["grups_relacionats"]),
            "viasona_link": viasona_link,
        }

        result.append(item)

    return result


# ---------------------------------------------------------------------
# CANÇONS
# ---------------------------------------------------------------------

def get_songs_info(cursor):
    """
    Exporta informació útil de cançons:

    - id_lletra
    - artista
    - titol
    - album
    - lletra
    - autor
    - compositor
    - durada
    - data
    - link intern de Viasona

    Guarda només lletres actives, visibles i de tipus 'lletra'.
    """

    sql = """
        SELECT
            gl.id_lletra,
            gl.titol AS titol_canco,
            gl.uri AS uri_canco,
            gl.contingut AS lletra,
            gl.autor,
            gl.compositor,
            gl.temps,
            gl.data,

            COALESCE(g_rel.titol, g_directe.titol) AS nom_grup,
            COALESCE(gd_rel.titol, gd_directe.titol) AS titol_album

        FROM grups_lletres gl

        LEFT JOIN grups_lletres_rel glr
            ON gl.id_lletra = glr.id_lletra

        LEFT JOIN grups g_rel
            ON glr.id_grup = g_rel.id_grup

        LEFT JOIN grups g_directe
            ON gl.id_grup_vell = g_directe.id_grup

        LEFT JOIN grups_discos_lletres_rel gdlr
            ON gl.id_lletra = gdlr.id_lletra

        LEFT JOIN grups_discos gd_rel
            ON gdlr.id_disc = gd_rel.id_disc

        LEFT JOIN grups_discos gd_directe
            ON gl.id_disc_vell = gd_directe.id_disc

        WHERE gl.estat = 'actiu'
          AND gl.tipus = 'lletra'
          AND gl.oculta = 'false'
          AND gl.contingut IS NOT NULL
          AND gl.contingut <> ''
    """

    cursor.execute(sql)
    rows = cursor.fetchall()

    if not rows:
        return []

    df = pd.DataFrame(rows)

    df["nom_grup"] = df["nom_grup"].apply(clean_html)
    df["titol_canco"] = df["titol_canco"].apply(clean_html)
    df["titol_album"] = df["titol_album"].apply(clean_html)
    df["lletra"] = df["lletra"].apply(clean_html)
    df["autor"] = df["autor"].apply(clean_html)
    df["compositor"] = df["compositor"].apply(clean_html)
    df["uri_canco"] = df["uri_canco"].fillna("").astype(str)

    df = df[df["lletra"].str.strip() != ""]

    grouped = (
        df.groupby(
            ["nom_grup", "lletra", "titol_canco"],
            dropna=False,
            as_index=False
        )
        .agg({
            "titol_album": join_unique,
            "id_lletra": "min",
            "uri_canco": first_non_empty,
            "autor": join_unique,
            "compositor": join_unique,
            "temps": first_non_empty,
            "data": first_non_empty,
        })
    )

    # Si una cançó apareix amb artista i també sense artista,
    # eliminem la versió sense artista.
    titles_with_artist = set(
        grouped[grouped["nom_grup"].notna() & (grouped["nom_grup"] != "")]["titol_canco"]
    )

    to_delete = (
        (grouped["nom_grup"].isna() | (grouped["nom_grup"] == ""))
        & grouped["titol_canco"].isin(titles_with_artist)
    )

    grouped = grouped[~to_delete].copy()

    grouped.rename(
        columns={
            "nom_grup": "artista",
            "titol_canco": "titol",
            "titol_album": "album",
        },
        inplace=True,
    )

    result = []

    for _, row in grouped.iterrows():
        id_lletra = row["id_lletra"]
        uri_canco = row["uri_canco"]

        item = {
            "id_lletra": int(id_lletra) if pd.notna(id_lletra) else "",
            "artista": row["artista"] if pd.notna(row["artista"]) else "",
            "titol": row["titol"] if pd.notna(row["titol"]) else "",
            "album": row["album"] if pd.notna(row["album"]) else "",
            "lletra": row["lletra"] if pd.notna(row["lletra"]) else "",
            "autor": row["autor"] if pd.notna(row["autor"]) else "",
            "compositor": row["compositor"] if pd.notna(row["compositor"]) else "",
            "durada": str(row["temps"]) if pd.notna(row["temps"]) else "",
            "data": str(row["data"]) if pd.notna(row["data"]) else "",
            "viasona_link": build_song_link(id_lletra, uri_canco),
        }

        result.append(item)

    return result


# ---------------------------------------------------------------------
# FUNCIÓ PRINCIPAL
# ---------------------------------------------------------------------

def get_info(db_config, news_csv_path, groups_csv_path, songs_csv_path):
    """
    1. Connecta a la base de dades.
    2. Extreu notícies.
    3. Extreu grups.
    4. Extreu cançons.
    5. Guarda els tres CSV.
    """

    connection = pymysql.connect(
        host=db_config["host"],
        port=db_config.get("port", 3306),
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        charset="utf8mb4",
        cursorclass=DictCursor,
    )

    try:
        with connection.cursor() as cursor:
            news_info = get_news_info(cursor)
            groups_info = get_groups_info(cursor)
            songs_info = get_songs_info(cursor)

            save_info(news_info, news_csv_path)
            save_info(groups_info, groups_csv_path)
            save_info(songs_info, songs_csv_path)

            return {
                "news_rows": len(news_info),
                "groups_rows": len(groups_info),
                "songs_rows": len(songs_info),
                "news_csv_path": str(news_csv_path),
                "groups_csv_path": str(groups_csv_path),
                "songs_csv_path": str(songs_csv_path),
            }

    finally:
        connection.close()


# ---------------------------------------------------------------------
# EXECUCIÓ
# ---------------------------------------------------------------------

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent          # backend/core
    BACKEND_DIR = BASE_DIR.parent                      # backend
    APP_DIR = BACKEND_DIR.parent                       # app
    PROJECT_DIR = APP_DIR.parent                       # semantic-song-search-engine

    DATA_DIR = BACKEND_DIR / "data"
    ENV_PATH = PROJECT_DIR / ".env"

    load_dotenv(ENV_PATH)

    required_vars = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        raise ValueError(
            f"Falten variables al fitxer .env: {missing}. "
            f"S'ha buscat el fitxer aquí: {ENV_PATH}"
        )

    db_config = {
        "host": os.getenv("DB_HOST"),
        "port": int(os.getenv("DB_PORT")),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
    }

    result = get_info(
        db_config=db_config,
        news_csv_path=DATA_DIR / "noticies.csv",
        groups_csv_path=DATA_DIR / "grups.csv",
        songs_csv_path=DATA_DIR / "cancons.csv",
    )

    print(result)