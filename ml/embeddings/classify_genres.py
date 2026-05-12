"""
Zero-shot genre classification of catalogue songs.

Encodes a small set of genre labels with BAAI/bge-m3 (the same model that
produced ``embedded_songs.parquet``) and scores every song against every
label by cosine similarity. The softmax over those scores is the per-song
"genre profile" used downstream by ``data_pipeline.py`` to bias the 2-D
projection toward genre clusters.

Output:
    app/backend/data/embedded_songs_genres.parquet
        id_lyrics    (int64)
        genre        (str)        — argmax label slug (key of ``GENRE_LABELS``)
        genre_scores (list[float]) — softmaxed similarities aligned with
                                     ``list(GENRE_LABELS.keys())``

Calibration
-----------
Zero-shot text-similarity is uncalibrated: rock songs frequently share
vocabulary with pop or punk and get pulled into those classes. Pass
``--prior <preset>`` (or ``--prior rock=0.30,pop=0.25,...``) to apply
Bayes-style log-ratio correction toward a target corpus distribution. Default
is the ``catalan`` preset — see ``TARGET_PRIORS`` below.

Usage:
    .venv/bin/python -m ml.embeddings.classify_genres
    .venv/bin/python -m ml.embeddings.classify_genres --prior none
    .venv/bin/python -m ml.embeddings.classify_genres --prior uniform
    .venv/bin/python -m ml.embeddings.classify_genres --prior rock=0.35,pop=0.30,cançó-autor=0.20,folk=0.05,rumba=0.05,electronica=0.02,hip-hop=0.02,punk=0.01
    .venv/bin/python -m ml.embeddings.classify_genres --temperature 25
    .venv/bin/python -m ml.embeddings.classify_genres --model BAAI/bge-m3
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import torch
from transformers import AutoModel, AutoTokenizer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Genre vocabulary.
#
# Slug (machine key) → human-readable description fed to the encoder.
# Labels are intentionally in Catalan because the corpus is Catalan music and
# bge-m3 is multilingual. Edit this dict to add / remove / rephrase genres.
#
# After editing, re-run this script AND regenerate the projection.
# The frontend ``genreColors.js`` must contain a colour for every slug, or new
# genres fall back to the default grey.
# ─────────────────────────────────────────────────────────────────────────────
GENRE_LABELS: dict[str, str] = {
    "pop":         "cançó pop catalana, melodies lleugeres i estribillos enganxosos",
    "rock":        "rock català amb guitarres elèctriques distorsionades i bateria potent",
    "folk":        "música folk tradicional catalana, acústica i amb arrels populars",
    "electronica": "música electrònica de ball amb sintetitzadors, techno i house",
    "hip-hop":     "hip-hop i rap català, beats urbans i lletres rimades",
    "rumba":       "rumba catalana festiva, palmes i guitarra espanyola",
    "cançó-autor": "cançó d'autor introspectiva, veu i guitarra acústica",
    "punk":        "punk rock català, ràpid, energètic i reivindicatiu",
}

# ─────────────────────────────────────────────────────────────────────────────
# Genre priors (calibration targets).
#
# Zero-shot text-similarity has no notion of base rates: rock songs that share
# vocabulary with pop or punk get systematically pulled into those classes.
# We correct for this with a Bayes-style log-ratio shift toward a *target*
# corpus distribution.  Pick a preset via ``--prior`` or pass explicit weights
# (``--prior rock=0.30,pop=0.25,...``).  ``--prior none`` disables.
# ─────────────────────────────────────────────────────────────────────────────
TARGET_PRIORS: dict[str, dict[str, float]] = {
    # Big three dominant but smaller classes still get real representation.
    # Designed to be paired with a sharper temperature (~80) so the raw signal
    # is informative enough to keep minority classes off the argmax floor.
    "catalan": {
        "cançó-autor": 0.22,
        "pop":         0.22,
        "rock":        0.22,
        "folk":        0.10,
        "rumba":       0.10,
        "electronica": 0.06,
        "hip-hop":     0.05,
        "punk":        0.03,
    },
    # Uniform — useful as a diagnostic.
    "uniform": {slug: 1 / 8 for slug in (
        "pop","rock","folk","electronica","hip-hop","rumba","cançó-autor","punk",
    )},
}

DEFAULT_MODEL       = "BAAI/bge-m3"
DEFAULT_TEMPERATURE = 20.0   # softmax sharpness: higher = more peaked
DEFAULT_PRIOR       = "none" # disabled by default; pass --prior catalan|uniform|...
                             # to recalibrate toward a target distribution
LABEL_PREFIX        = ""     # bge-m3 does not use prefixes


_DATA_DIR    = Path(__file__).resolve().parents[2] / "app" / "backend" / "data"
_EMBED_FILE  = _DATA_DIR / "embedded_songs.parquet"
_OUTPUT_FILE = _DATA_DIR / "embedded_songs_genres.parquet"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _parse_embedding(val) -> np.ndarray:
    """Parquet stores embeddings as ``"[v1, v2, ...]"`` strings."""
    if isinstance(val, str):
        return np.fromstring(val.strip("[]"), sep=",", dtype=np.float32)
    return np.asarray(val, dtype=np.float32)


def _load_songs() -> tuple[np.ndarray, np.ndarray]:
    if not _EMBED_FILE.exists():
        raise FileNotFoundError(
            f"Embeddings parquet not found at {_EMBED_FILE}. "
            "Generate it with the embedding pipeline first."
        )
    logger.info("Reading %s …", _EMBED_FILE)
    df = pq.read_table(
        _EMBED_FILE, columns=["id_lyrics", "embedded_lyrics"]
    ).to_pandas()
    ids = df["id_lyrics"].astype("int64").to_numpy()
    matrix = np.vstack([_parse_embedding(v) for v in df["embedded_lyrics"]])
    matrix = matrix.astype(np.float32)
    logger.info("Loaded %d songs, embedding dim %d", matrix.shape[0], matrix.shape[1])
    return ids, matrix


def _encode_labels(model_name: str, expected_dim: int) -> tuple[list[str], np.ndarray]:
    """Encode every label in ``GENRE_LABELS`` to an L2-normed vector."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading %s on %s …", model_name, device)
    tok = AutoTokenizer.from_pretrained(model_name)
    mdl = AutoModel.from_pretrained(model_name).to(device).eval()

    texts = [f"{LABEL_PREFIX}{label}" for label in GENRE_LABELS.values()]
    enc = tok(
        texts, padding=True, truncation=True, max_length=128, return_tensors="pt"
    ).to(device)
    with torch.no_grad():
        out = mdl(**enc)
    # bge-m3 dense-retrieval head uses the [CLS] token at position 0.
    pooled = out.last_hidden_state[:, 0]
    pooled = torch.nn.functional.normalize(pooled, p=2, dim=-1)
    vecs   = pooled.cpu().numpy().astype(np.float32)

    if vecs.shape[1] != expected_dim:
        raise ValueError(
            f"Label embeddings have dim {vecs.shape[1]} but songs have dim "
            f"{expected_dim}. Use BAAI/bge-m3 (1024-dim) — the model that "
            "produced embedded_songs.parquet."
        )
    return list(GENRE_LABELS.keys()), vecs


def _softmax(logits: np.ndarray, temperature: float) -> np.ndarray:
    """Row-wise softmax with temperature; numerically stable."""
    scaled = logits * temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exp = np.exp(scaled, dtype=np.float64)
    return (exp / exp.sum(axis=1, keepdims=True)).astype(np.float32)


def _parse_prior(spec: str, slugs: list[str]) -> np.ndarray | None:
    """Resolve a ``--prior`` argument to a normalised (G,) target vector.

    Accepts: ``none``, a preset name (``catalan``/``uniform``), or an explicit
    comma-separated list like ``rock=0.30,pop=0.25``.  Missing slugs default
    to 0 — explicit weights are normalised so they sum to 1.
    """
    if spec is None or spec.lower() == "none":
        return None

    if spec in TARGET_PRIORS:
        weights = TARGET_PRIORS[spec]
    else:
        weights = {}
        for part in spec.split(","):
            if "=" not in part:
                raise ValueError(f"Bad --prior token: {part!r}. Use slug=value.")
            k, v = part.split("=", 1)
            weights[k.strip()] = float(v)

    target = np.array([weights.get(s, 0.0) for s in slugs], dtype=np.float64)
    if target.sum() <= 0:
        raise ValueError(f"--prior {spec!r} contains no positive weight.")
    return target / target.sum()


def _apply_prior_correction(profile: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Re-balance a softmaxed profile toward ``target``.

    Standard zero-shot calibration: multiply every row by ``target / empirical``
    where ``empirical`` is the corpus-mean of the raw profile, then renormalise.
    Equivalent in log-space to adding ``log(target/empirical)`` to the pre-softmax
    logits.

    Returns a new ``(N, G)`` profile whose corpus distribution lands near
    ``target``.  Per-song ranks are preserved within each class but the
    cross-class argmax shifts.
    """
    empirical = profile.mean(axis=0).astype(np.float64).clip(min=1e-9)
    ratio = target / empirical
    logger.info("Prior correction ratios (target / empirical):")
    for slug, r in zip(GENRE_LABELS.keys(), ratio):
        logger.info("  %-12s × %6.2f", slug, r)
    adjusted = profile.astype(np.float64) * ratio
    adjusted /= adjusted.sum(axis=1, keepdims=True)
    return adjusted.astype(np.float32)


# ─── Public entry point ─────────────────────────────────────────────────────

def _existing_distribution() -> dict | None:
    """Read the already-written parquet and return a summary dict.

    Used to short-circuit the classifier when the output is already on disk —
    avoids a 2 GB model re-download every time the script is invoked.
    """
    if not _OUTPUT_FILE.exists():
        return None
    df = pq.read_table(_OUTPUT_FILE, columns=["id_lyrics", "genre"]).to_pandas()
    counts = df["genre"].value_counts()
    logger.info(
        "Output %s already exists with %d rows — skipping. "
        "Pass --force to regenerate.", _OUTPUT_FILE, len(df),
    )
    logger.info("Genre distribution:\n%s", counts.to_string())
    return {
        "rows":         len(df),
        "labels":       list(GENRE_LABELS.keys()),
        "output_file":  str(_OUTPUT_FILE),
        "distribution": counts.to_dict(),
        "skipped":      True,
    }


def classify(
    model_name: str    = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    prior: str         = DEFAULT_PRIOR,
    force: bool        = False,
) -> dict:
    """Run zero-shot genre classification and write the parquet.

    If the output parquet already exists and ``force`` is False, the function
    short-circuits without loading the embedding model — no 2 GB download.
    """
    if not force:
        existing = _existing_distribution()
        if existing is not None:
            return existing

    ids, songs = _load_songs()
    slugs, label_vecs = _encode_labels(model_name, expected_dim=songs.shape[1])

    # Songs are already L2-normed by the embedding pipeline; cosine = dot.
    logger.info("Scoring %d songs × %d genres …", songs.shape[0], len(slugs))
    similarities = songs @ label_vecs.T               # (N, G) in [-1, 1]
    profile      = _softmax(similarities, temperature)

    target = _parse_prior(prior, slugs)
    if target is not None:
        before = profile.mean(axis=0)
        logger.info("Raw distribution (pre-calibration):")
        for slug, p in zip(slugs, before):
            logger.info("  %-12s %5.1f%%", slug, 100 * p)
        profile = _apply_prior_correction(profile, target)

    argmax = profile.argmax(axis=1)
    genres = [slugs[int(i)] for i in argmax]

    out = pd.DataFrame({
        "id_lyrics":    ids,
        "genre":        genres,
        "genre_scores": list(profile),   # each row a (G,) float32 array
    })

    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _OUTPUT_FILE.exists():
        _OUTPUT_FILE.unlink()
    out.to_parquet(_OUTPUT_FILE, index=False)

    counts = out["genre"].value_counts()
    logger.info("Wrote %d rows to %s", len(out), _OUTPUT_FILE)
    logger.info("Genre distribution:\n%s", counts.to_string())
    return {
        "rows":         len(out),
        "labels":       slugs,
        "output_file":  str(_OUTPUT_FILE),
        "distribution": counts.to_dict(),
    }


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Zero-shot genre classifier.")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"HuggingFace model id (default: {DEFAULT_MODEL}).")
    p.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                   help="Softmax temperature; higher = peakier (default: %(default)s).")
    p.add_argument("--prior", default=DEFAULT_PRIOR,
                   help=("Prior-correction target. Presets: " +
                         ", ".join(TARGET_PRIORS) + ". Use 'none' to disable, or "
                         "an explicit list like 'rock=0.30,pop=0.25,...' "
                         "(default: %(default)s)."))
    p.add_argument("--force", action="store_true",
                   help="Regenerate even if the output parquet already exists "
                        "(downloads the embedding model if not cached).")
    args = p.parse_args()
    classify(
        model_name=args.model, temperature=args.temperature,
        prior=args.prior, force=args.force,
    )
