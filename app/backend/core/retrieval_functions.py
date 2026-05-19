from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# Map known filenames to their split-layout subdirectory. Anything else
# falls back to DATA_DIR so old callers don't break catastrophically.
_LOCATION = {
    "embedded_songs.parquet":     RAW_DIR,
    "augmented_songs.csv":        RAW_DIR,
    "cancons.csv":                RAW_DIR,
    "grups.csv":                  RAW_DIR,
    "noticies.csv":               RAW_DIR,
    "embedded_songs_2d.parquet":          PROCESSED_DIR,
    "embedded_songs_top5000.parquet":     PROCESSED_DIR,
    "embedded_songs_genres.parquet":      PROCESSED_DIR,
    "songs_meta.parquet":                 PROCESSED_DIR,
    "top_5000_songs.csv":                 PROCESSED_DIR,
}


def data_path(filename):
    return _LOCATION.get(filename, DATA_DIR) / filename


def id2emb(target_id, file="embedded_songs.parquet"):
    file_path = data_path(file)

    table = pq.read_table(
        file_path,
        filters=[("id_lyrics", "==", target_id)],
        columns=[
            "id_lyrics",
            "embedded_lyrics",
            "embedded_qualitative_description",
            "embedded_title",
            "embedded_album",
            "embedded_artist",
        ],
    )

    df = table.to_pandas()

    if df.empty:
        raise ValueError(f"No embedding found with id_lyrics={target_id}")

    return df.iloc[0]


def id2content(target_id, file="augmented_songs.csv"):
    file_path = data_path(file)

    df = pd.read_csv(file_path)

    result = df[df["id_lyrics"] == target_id][
        [
            "id_lyrics",
            "lyrics",
            "qualitative_description",
            "title",
            "album",
            "artist",
        ]
    ]

    if result.empty:
        raise ValueError(f"No song found with id_lyrics={target_id}")

    return result.iloc[0]


def id_2Demb(target_id, file="embedded_songs_2d.parquet", method=None):
    file_path = data_path(file)

    filters = [("id_lyrics", "==", target_id)]

    if method is not None:
        filters.append(("method", "==", method.lower()))

    table = pq.read_table(
        file_path,
        filters=filters,
        columns=["id_lyrics", "x", "y", "method"],
    )

    df = table.to_pandas()

    if df.empty:
        raise ValueError(f"No 2D embedding found with id_lyrics={target_id}")

    return df.iloc[0]