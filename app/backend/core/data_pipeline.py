from pathlib import Path

import pandas as pd

from app.backend.core.data_loader import load_all_songs
from app.backend.core.projections import _run_tsne, _songs_to_matrix


_DATA_DIR = Path(__file__).parent.parent / "data"
_OUTPUT = _DATA_DIR / "embedded_songs_2d.parquet"


def run_pipeline(limit: int | None = None) -> dict:
    songs = load_all_songs()

    if limit is not None:
        songs = songs[:limit]

    if not songs:
        raise ValueError("No songs loaded — check that embedded_songs.parquet exists.")

    print(f"Projecting {len(songs)} songs with t-SNE...")
    matrix = _songs_to_matrix(songs)
    coords = _run_tsne(matrix, n_components=2)

    result = pd.DataFrame({
        "id_lyrics": [s["id"] for s in songs],
        "x": coords[:, 0],
        "y": coords[:, 1],
    })

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(_OUTPUT, index=False)

    print(f"Done — {len(result)} rows written to {_OUTPUT}")
    return {"rows": len(result), "output_file": str(_OUTPUT)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate 2D song projections from embeddings.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of songs to process (default: all)")
    args = parser.parse_args()

    run_pipeline(limit=args.limit)
