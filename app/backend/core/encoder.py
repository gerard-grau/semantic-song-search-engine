"""
Embedding model configuration — edit this file when switching models.

After changing MODEL_NAME / PASSAGE_PREFIX or build_song_passage(), re-run:
    .venv/bin/python scripts/reembed_mock_songs.py
to regenerate the stored song embeddings.
"""

from __future__ import annotations

import logging

import torch

logger = logging.getLogger(__name__)

# ── Change these when switching models ────────────────────────────────────────
MODEL_NAME     = "intfloat/multilingual-e5-small"
MODEL_DIM      = 384        # output dimension; must match MODEL_NAME
QUERY_PREFIX   = "query: "  # prepended to search queries at inference time
PASSAGE_PREFIX = "passage: "  # prepended to song texts at embedding time


def build_song_passage(song: dict) -> str:
    """
    Text fed to the encoder when embedding a song.

    Change this if you want to use different fields or a different format.
    Re-run scripts/reembed_mock_songs.py after any change here.
    """
    title   = song.get("title",          "").strip()
    artist  = song.get("artist",         "").strip()
    snippet = song.get("lyrics_snippet", "").strip()
    genre   = song.get("genre",          "").strip()
    return f"{PASSAGE_PREFIX}{title} by {artist}. Genre: {genre}. {snippet}"


# ── Model cache (one instance per process) ────────────────────────────────────

_tokenizer = None
_model     = None
_device    = None


def load_encoder():
    """Load MODEL_NAME once and cache it for the lifetime of the process."""
    global _tokenizer, _model, _device
    if _model is not None:
        return _tokenizer, _model, _device
    from transformers import AutoModel, AutoTokenizer
    _device    = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading %s on %s …", MODEL_NAME, _device)
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    _model     = AutoModel.from_pretrained(MODEL_NAME).to(_device)
    _model.eval()
    logger.info("Model ready.")
    return _tokenizer, _model, _device


# ── Internal helpers ──────────────────────────────────────────────────────────

def _mean_pool(token_emb: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).float()
    return (token_emb * mask).sum(1) / mask.sum(1).clamp(min=1e-9)


# ── Public encoding API ───────────────────────────────────────────────────────

def encode_query(text: str) -> list[float]:
    """
    Encode a user search query.

    Prepends QUERY_PREFIX before encoding.
    Returns an L2-normalised MODEL_DIM vector.
    """
    tokenizer, model, device = load_encoder()
    enc = tokenizer(
        [f"{QUERY_PREFIX}{text}"],
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt",
    ).to(device)
    with torch.no_grad():
        out = model(**enc)
    vec = _mean_pool(out.last_hidden_state, enc["attention_mask"])
    vec = torch.nn.functional.normalize(vec, p=2, dim=-1)
    return vec[0].cpu().tolist()


@torch.no_grad()
def encode_passages(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """
    Encode a list of passage strings in batches.

    Used by scripts/reembed_mock_songs.py.
    Returns a list of L2-normalised MODEL_DIM vectors.
    """
    tokenizer, model, device = load_encoder()
    all_vecs: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        enc = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(device)
        out = model(**enc)
        vecs = _mean_pool(out.last_hidden_state, enc["attention_mask"])
        vecs = torch.nn.functional.normalize(vecs, p=2, dim=-1)
        all_vecs.extend(vecs.cpu().tolist())
        print(f"  encoded {min(i + batch_size, len(texts))}/{len(texts)}", end="\r")
    print()
    return all_vecs
