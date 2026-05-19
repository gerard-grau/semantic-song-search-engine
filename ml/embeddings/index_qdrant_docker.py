"""
Indexes song embeddings into a Docker-hosted Qdrant instance.

Two collections are created (or recreated from scratch):

  songs_qualitative   — one point per song.
                        Vector: embedded_qualitative_description (1024-dim BGE-M3).
                        Reuses the already-computed vectors from the batch parquets
                        in embedded_songs_dataset/ — no re-embedding needed.

  songs_lyrics_chunks — one point per ~40-word chunk of a song's lyrics.
                        Vector: BGE-M3 embedding of lowercased chunk text.
                        Chunking with 20-word overlap improves short-query recall vs.
                        whole-song embeddings because the query is compared against the
                        most relevant passage, not a diluted full-song average.

Run after starting Qdrant (Docker or native binary):

  sudo docker run -d --name qdrant_server \\
      -p 6333:6333 -p 6334:6334 \\
      qdrant/qdrant

Usage:
  python -m ml.embeddings.index_qdrant_docker
  python -m ml.embeddings.index_qdrant_docker --only-qualitative
  python -m ml.embeddings.index_qdrant_docker --only-lyrics
  python -m ml.embeddings.index_qdrant_docker --only-lyrics --resume
"""

from __future__ import annotations

import argparse
import gc
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
CHUNK_WORDS     = 40    # words per chunk
CHUNK_OVERLAP   = 20    # overlap between consecutive chunks (stride = 20)
MIN_CHUNK_WORDS = 8     # discard trailing chunks shorter than this

# ── Encoder batch size (adjust down if you run out of RAM/VRAM) ───────────────
EMBED_BATCH  = 16   # embeddings per model forward pass
UPLOAD_EVERY = 500  # upload to Qdrant after this many chunks (controls peak RAM)

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO_ROOT     = Path(__file__).resolve().parent.parent.parent
_PARQUET_DIR   = Path(__file__).resolve().parent / "embedded_songs_dataset"
_CSV_PATH      = _REPO_ROOT / "data" / "processed" / "augmented_songs.csv"
_PROGRESS_FILE = Path(__file__).resolve().parent / ".lyrics_index_progress"


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


def _read_progress() -> int:
    """Return the last song_i that was fully committed, or -1 if none."""
    if _PROGRESS_FILE.exists():
        try:
            return int(_PROGRESS_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return -1


def _write_progress(song_i: int) -> None:
    _PROGRESS_FILE.write_text(str(song_i))


def _clear_progress() -> None:
    _PROGRESS_FILE.unlink(missing_ok=True)


# ── Qualitative collection ────────────────────────────────────────────────────

def index_qualitative(client: QdrantClient) -> None:
    """Upload qualitative_description embeddings reusing the existing parquets."""
    print("\n=== Indexing 'songs_qualitative' collection ===")

    if client.collection_exists(QUALITATIVE_COLLECTION):
        client.delete_collection(QUALITATIVE_COLLECTION)
        print(f"  Deleted existing '{QUALITATIVE_COLLECTION}'")

    client.create_collection(
        collection_name=QUALITATIVE_COLLECTION,
        vectors_config={
            "embedded_qualitative_description": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            "embedded_title":                   VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        },
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
            vec_qual = row["embedded_qualitative_description"]
            if vec_qual is None:
                continue
            if hasattr(vec_qual, "tolist"):
                vec_qual = vec_qual.tolist()
            if not isinstance(vec_qual, list) or len(vec_qual) != VECTOR_DIM:
                continue

            vec_title = row.get("embedded_title")
            if vec_title is not None and hasattr(vec_title, "tolist"):
                vec_title = vec_title.tolist()
            if not isinstance(vec_title, list) or len(vec_title) != VECTOR_DIM:
                vec_title = vec_qual  # fallback to qualitative if title missing

            pid = _gen_id(f"qual_{row['id_lyrics']}_{row['artist']}")
            points.append(PointStruct(
                id=pid,
                vector={
                    "embedded_qualitative_description": _normalise(vec_qual),
                    "embedded_title":                   _normalise(vec_title),
                },
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

def index_lyrics_chunks(client: QdrantClient, resume: bool = False) -> None:
    """Chunk lyrics, embed with BGE-M3, upload to the lyrics-chunks collection.

    With resume=True the existing collection is kept and indexing continues
    from the last successfully committed song (tracked in _PROGRESS_FILE).
    Point IDs are deterministic UUIDs so any overlap is safely upserted.
    """
    print("\n=== Indexing 'songs_lyrics_chunks' collection ===")

    resume_from = -1  # song_i of last committed batch; skip song_i <= resume_from

    if resume:
        if not client.collection_exists(LYRICS_COLLECTION):
            print("  --resume requested but collection doesn't exist — starting fresh.")
            resume = False
        else:
            resume_from = _read_progress()
            if resume_from < 0:
                print("  --resume requested but no progress file found — starting fresh.")
                resume = False
            else:
                print(f"  Resuming from song index {resume_from + 1} "
                      f"(skipping first {resume_from + 1} songs).")

    if not resume:
        if client.collection_exists(LYRICS_COLLECTION):
            client.delete_collection(LYRICS_COLLECTION)
            print(f"  Deleted existing '{LYRICS_COLLECTION}'")
        _clear_progress()
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

    buf_texts:  list[str]  = []
    buf_meta:   list[dict] = []
    songs_with_no_lyrics   = 0
    total_uploaded         = 0
    last_flushed_song_i    = resume_from  # tracks progress for the file

    # current_song_i is updated by the main loop before each _flush() call
    # so _flush() knows which song triggered it.
    _cursor: list[int] = [resume_from]

    def _flush(force: bool = False) -> None:
        nonlocal total_uploaded, last_flushed_song_i
        if not buf_texts:
            return
        if not force and len(buf_texts) < UPLOAD_EVERY:
            return
        vecs = encode_passages(buf_texts, batch_size=EMBED_BATCH)
        points = [
            PointStruct(
                id=_gen_id(f"chunk_{m['id_lyrics']}_{m['artist']}_{m['chunk_idx']}"),
                vector=_normalise(v),
                payload=m,
            )
            for v, m in zip(vecs, buf_meta)
        ]
        client.upload_points(LYRICS_COLLECTION, points)
        total_uploaded += len(points)
        last_flushed_song_i = _cursor[0]
        _write_progress(last_flushed_song_i)
        print(f"  Uploaded {total_uploaded} chunks so far "
              f"(progress saved at song {last_flushed_song_i}) …")
        buf_texts.clear()
        buf_meta.clear()
        gc.collect()

    for song_i, (_, row) in enumerate(df.iterrows()):
        if song_i <= resume_from:
            continue  # already in Qdrant

        _cursor[0] = song_i

        chunks = _chunk_lyrics(str(row.get("lyrics", "")))
        if not chunks:
            songs_with_no_lyrics += 1
            continue
        for ci, chunk in enumerate(chunks):
            buf_texts.append(chunk)
            buf_meta.append({
                "id_lyrics":          int(row["id_lyrics"]),
                "artist":             str(row["artist"]),
                "title":              str(row.get("title", "")),
                "album":              str(row.get("album", "")),
                "chunk_idx":          ci,
                "chunk_text_snippet": chunk[:250],
            })
        _flush()

        if song_i % 5000 == 0 and song_i > 0:
            print(f"  … processed {song_i}/{len(df)} songs")

    _flush(force=True)
    _clear_progress()
    print(f"  ({songs_with_no_lyrics} songs skipped — no lyrics)")
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
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume lyrics indexing from last saved checkpoint (keeps existing collection)",
    )
    args = parser.parse_args()

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    print(f"Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")

    if not args.only_lyrics:
        index_qualitative(client)
    if not args.only_qualitative:
        index_lyrics_chunks(client, resume=args.resume)

    client.close()
    print("\nAll done.")


if __name__ == "__main__":
    main()
