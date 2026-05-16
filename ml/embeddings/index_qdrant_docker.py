"""
Indexes song embeddings into a Docker-hosted Qdrant instance.

Two collections are created (or recreated from scratch):

  songs_qualitative   — one point per song.
                        Vector: embedded_qualitative_description (1024-dim BGE-M3).
                        Reuses the already-computed vectors from the batch parquets
                        in embedded_songs_dataset/ — no re-embedding needed.

  songs_lyrics_chunks — one point per ~100-word chunk of a song's lyrics.
                        Vector: BGE-M3 embedding of lowercased chunk text.
                        Chunking with 50-word overlap improves short-query recall vs.
                        whole-song embeddings because the query is compared against the
                        most relevant passage, not a diluted full-song average.

Run after starting Docker Qdrant:

  sudo docker run -d --name qdrant_server \\
      -p 6333:6333 -p 6334:6334 \\
      qdrant/qdrant

Usage:
  python -m ml.embeddings.index_qdrant_docker
  python -m ml.embeddings.index_qdrant_docker --only-qualitative
  python -m ml.embeddings.index_qdrant_docker --only-lyrics
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# ── Qdrant target ─────────────────────────────────────────────────────────────
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333

QUALITATIVE_COLLECTION = "songs_qualitative"
LYRICS_COLLECTION      = "songs_lyrics_chunks"
VECTOR_DIM             = 1024   # BAAI/bge-m3 dense output dimension

# ── Lyrics chunking ───────────────────────────────────────────────────────────
CHUNK_WORDS     = 100   # words per chunk
CHUNK_OVERLAP   = 50    # overlap between consecutive chunks (stride = 50)
MIN_CHUNK_WORDS = 15    # discard trailing chunks shorter than this

# ── Encoder batch size (adjust down if you run out of RAM/VRAM) ───────────────
EMBED_BATCH = 32

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
_PARQUET_DIR = Path(__file__).resolve().parent / "embedded_songs_dataset"
_CSV_PATH    = _REPO_ROOT / "data" / "processed" / "augmented_songs.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_id(val: str) -> str:
    """Deterministic UUID-5 from a string key."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, val))


def _normalise(vec: list[float]) -> list[float]:
    """L2-normalise a float list; return as-is if zero vector."""
    arr = np.array(vec, dtype=np.float32)
    n = float(np.linalg.norm(arr))
    if n > 1e-9:
        arr = arr / n
    return arr.tolist()


def _chunk_lyrics(lyrics: str) -> list[str]:
    """Split lyrics into overlapping word-level chunks, lowercased."""
    if not isinstance(lyrics, str) or not lyrics.strip():
        return []
    words = lyrics.lower().split()
    if len(words) < MIN_CHUNK_WORDS:
        return [" ".join(words)]
    chunks: list[str] = []
    step = CHUNK_WORDS - CHUNK_OVERLAP
    for start in range(0, len(words), step):
        chunk = words[start : start + CHUNK_WORDS]
        if len(chunk) < MIN_CHUNK_WORDS:
            break
        chunks.append(" ".join(chunk))
    return chunks


def _load_meta_csv() -> pd.DataFrame:
    return pd.read_csv(_CSV_PATH, encoding="utf-8-sig")[
        ["id_lyrics", "artist", "title", "album", "lyrics"]
    ].fillna("")


# ── Qualitative collection ────────────────────────────────────────────────────

def index_qualitative(client: QdrantClient) -> None:
    """Upload qualitative_description embeddings reusing the existing parquets."""
    print("\n=== Indexing 'songs_qualitative' collection ===")

    if client.collection_exists(QUALITATIVE_COLLECTION):
        client.delete_collection(QUALITATIVE_COLLECTION)
        print(f"  Deleted existing '{QUALITATIVE_COLLECTION}'")

    client.create_collection(
        collection_name=QUALITATIVE_COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print(f"  Created '{QUALITATIVE_COLLECTION}'")

    df_meta = _load_meta_csv()[["id_lyrics", "artist", "title", "album"]]

    total = 0
    for fname in sorted(os.listdir(_PARQUET_DIR)):
        if not fname.endswith(".parquet"):
            continue
        fpath = os.path.join(_PARQUET_DIR, fname)
        df = pd.read_parquet(fpath)

        if "embedded_qualitative_description" not in df.columns:
            print(f"  skip {fname} — no qualitative_description column")
            continue

        df = df.merge(df_meta, on=["id_lyrics", "artist"], how="left")
        df["title"] = df["title"].fillna("")
        df["album"] = df["album"].fillna("")

        points: list[PointStruct] = []
        for _, row in df.iterrows():
            vec = row["embedded_qualitative_description"]
            if vec is None:
                continue
            if hasattr(vec, "tolist"):
                vec = vec.tolist()
            if not isinstance(vec, list) or len(vec) != VECTOR_DIM:
                continue
            pid = _gen_id(f"qual_{row['id_lyrics']}_{row['artist']}")
            points.append(PointStruct(
                id=pid,
                vector=_normalise(vec),
                payload={
                    "id_lyrics": int(row["id_lyrics"]),
                    "artist":    str(row["artist"]),
                    "title":     str(row["title"]),
                    "album":     str(row["album"]),
                },
            ))

        if points:
            client.upload_points(QUALITATIVE_COLLECTION, points)
            total += len(points)
            print(f"  {fname}: {len(points)} songs  (running total {total})")

    print(f"\nQualitative collection complete: {total} songs indexed.")


# ── Lyrics-chunks collection ──────────────────────────────────────────────────

def index_lyrics_chunks(client: QdrantClient) -> None:
    """Chunk lyrics, embed with BGE-M3, upload to the lyrics-chunks collection."""
    print("\n=== Indexing 'songs_lyrics_chunks' collection ===")

    if client.collection_exists(LYRICS_COLLECTION):
        client.delete_collection(LYRICS_COLLECTION)
        print(f"  Deleted existing '{LYRICS_COLLECTION}'")

    client.create_collection(
        collection_name=LYRICS_COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print(f"  Created '{LYRICS_COLLECTION}'")

    # Import the shared encoder (loads BAAI/bge-m3 once)
    sys.path.insert(0, str(_REPO_ROOT))
    from app.backend.core.encoder import encode_passages  # noqa: PLC0415

    df = _load_meta_csv()
    print(f"  Loaded {len(df)} songs from CSV")

    # Collect every chunk and its metadata up-front
    all_texts: list[str]  = []
    all_meta:  list[dict] = []
    songs_with_no_lyrics  = 0

    for _, row in df.iterrows():
        chunks = _chunk_lyrics(str(row.get("lyrics", "")))
        if not chunks:
            songs_with_no_lyrics += 1
            continue
        for ci, chunk in enumerate(chunks):
            all_texts.append(chunk)
            all_meta.append({
                "id_lyrics":          int(row["id_lyrics"]),
                "artist":             str(row["artist"]),
                "title":              str(row.get("title", "")),
                "album":              str(row.get("album", "")),
                "chunk_idx":          ci,
                "chunk_text_snippet": chunk[:250],
            })

    print(f"  {len(all_texts)} chunks from {len(df) - songs_with_no_lyrics} songs")
    print(f"  ({songs_with_no_lyrics} songs skipped — no lyrics)")

    # Embed + upload in super-batches (EMBED_BATCH * 10 texts at a time)
    SUPER = EMBED_BATCH * 10
    total_uploaded = 0

    for start in range(0, len(all_texts), SUPER):
        end         = min(start + SUPER, len(all_texts))
        batch_texts = all_texts[start:end]
        batch_meta  = all_meta[start:end]

        vecs = encode_passages(batch_texts, batch_size=EMBED_BATCH)

        points: list[PointStruct] = []
        for vec, meta in zip(vecs, batch_meta):
            pid = _gen_id(
                f"chunk_{meta['id_lyrics']}_{meta['artist']}_{meta['chunk_idx']}"
            )
            points.append(PointStruct(
                id=pid,
                vector=_normalise(vec),
                payload=meta,
            ))

        client.upload_points(LYRICS_COLLECTION, points)
        total_uploaded += len(points)
        print(f"  Uploaded {end}/{len(all_texts)} chunks  ({total_uploaded} total)")

    print(f"\nLyrics-chunks collection complete: {total_uploaded} chunks indexed.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index songs into Docker Qdrant at localhost:6333"
    )
    parser.add_argument(
        "--only-qualitative", action="store_true",
        help="Index only the qualitative_description collection",
    )
    parser.add_argument(
        "--only-lyrics", action="store_true",
        help="Index only the lyrics-chunks collection",
    )
    args = parser.parse_args()

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    print(f"Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")

    if not args.only_lyrics:
        index_qualitative(client)
    if not args.only_qualitative:
        index_lyrics_chunks(client)

    client.close()
    print("\nAll done.")


if __name__ == "__main__":
    main()
