"""
Re-embed mock_songs.json using the model configured in core/encoder.py.

Run from the repo root:
    .venv/bin/python scripts/reembed_mock_songs.py

Re-run this script any time you change MODEL_NAME, PASSAGE_PREFIX, or
build_song_passage() in app/backend/core/encoder.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add repo root to sys.path so the app package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.backend.core.encoder import (
    MODEL_NAME,
    build_song_passage,
    encode_passages,
    load_encoder,
)

DATA_PATH = Path(__file__).parent.parent / "app" / "backend" / "data" / "mock_songs.json"


def main() -> None:
    print(f"Loading {MODEL_NAME} …")
    load_encoder()

    print(f"Reading {DATA_PATH} …")
    songs = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"  {len(songs)} songs found.")

    passages = [build_song_passage(s) for s in songs]
    print("Example passage:")
    print(" ", passages[0])
    print()

    print("Encoding …")
    embeddings = encode_passages(passages)

    old_dim = len(songs[0].get("embedding") or [])
    new_dim = len(embeddings[0])
    print(f"Embedding dimension: {old_dim} → {new_dim}")

    for song, emb in zip(songs, embeddings):
        song["embedding"] = emb

    DATA_PATH.write_text(json.dumps(songs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved updated embeddings to {DATA_PATH}")


if __name__ == "__main__":
    main()
