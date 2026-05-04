from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
DATA_DIR = BACKEND_DIR / "data"


def data_path(filename):
    return DATA_DIR / filename


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