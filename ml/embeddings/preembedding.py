import ast
import torch
import numpy as np
import pandas as pd
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModel

# ── Config ────────────────────────────────────────────────────────────────────
CSV_PATH        = "../augmented_songs.csv"
OUTPUT_PATH     = "embedded_songs.pt"       # save as torch file
MODEL_NAME      = "BAAI/bge-m3"
BATCH_SIZE      = 64                        # number of text pieces per forward pass
DEVICE          = "cuda" if torch.cuda.is_available() else "cpu"

# ── Load model ────────────────────────────────────────────────────────────────
print(f"Loading {MODEL_NAME} on {DEVICE}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model     = AutoModel.from_pretrained(MODEL_NAME).to(DEVICE)
model.eval()

# ── Helpers ───────────────────────────────────────────────────────────────────
def cls_pool(token_embeddings: torch.Tensor) -> torch.Tensor:
    """bge-m3 dense-retrieval head uses the [CLS] token at position 0."""
    return token_embeddings[:, 0]

@torch.no_grad()
def embed_texts(texts: list[str]) -> torch.Tensor:
    """
    Embed a list of strings in batches.
    bge-m3 does not use prefixes (unlike multilingual-e5).
    Returns a (N, hidden_size) tensor.
    """
    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        ).to(DEVICE)
        output = model(**encoded)
        emb = cls_pool(output.last_hidden_state)
        emb = torch.nn.functional.normalize(emb, p=2, dim=-1)   # L2 normalize
        all_embeddings.append(emb.cpu())
    return torch.cat(all_embeddings, dim=0)

def aggregate_chunk_embeddings(chunk_embeddings: torch.Tensor) -> torch.Tensor:
    """Mean pool a (N_chunks, hidden_size) tensor → (hidden_size,)."""
    return chunk_embeddings.mean(dim=0)

# ── Main pipeline ─────────────────────────────────────────────────────────────
def preembed_songs(csv_path: str, output_path: str):
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} songs.")

    # Parse chunk columns back to lists
    df["lyrics_chunks"]  = df["lyrics_chunks"].apply(
        lambda x: ast.literal_eval(x) if isinstance(x, str) else []
    )
    df["noised_chunks"] = df["noised_chunks"].apply(
        lambda x: ast.literal_eval(x) if isinstance(x, str) else []
    )

    records = []
    for _, row in tqdm(df.iterrows(), total=len(df)):

        # bge-m3 does not use prefixes — feed raw text directly.
        chunks        = [c for c in row["lyrics_chunks"]  if isinstance(c, str)]
        noised_chunks = [c for c in row["noised_chunks"] if isinstance(c, str)]
        title         = row["title"]         if isinstance(row["title"],         str) else None
        noised_title  = row["noised_title"]  if isinstance(row["noised_title"],  str) else None
        author        = row["author"]        if isinstance(row["author"],        str) else None
        noised_author = row["noised_author"] if isinstance(row["noised_author"], str) else None

        # -- Embed chunks & aggregate --
        if chunks:
            chunk_embs        = embed_texts(chunks)
            song_emb          = aggregate_chunk_embeddings(chunk_embs)
        else:
            song_emb          = torch.zeros(1024)       # fallback for empty lyrics

        if noised_chunks:
            noised_chunk_embs = embed_texts(noised_chunks)
            noised_song_emb   = aggregate_chunk_embeddings(noised_chunk_embs)
        else:
            noised_song_emb   = torch.zeros(1024)

        # -- Embed title & author --
        title_emb         = embed_texts([title])[0]         if title         else torch.zeros(1024)
        noised_title_emb  = embed_texts([noised_title])[0]  if noised_title  else torch.zeros(1024)
        author_emb        = embed_texts([author])[0]        if author        else torch.zeros(1024)
        noised_author_emb = embed_texts([noised_author])[0] if noised_author else torch.zeros(1024)

        records.append({
            "song_id":          _,
            "song_emb":         song_emb,           # (1024,)
            "noised_song_emb":  noised_song_emb,    # (1024,)
            "title_emb":        title_emb,           # (1024,)
            "noised_title_emb": noised_title_emb,   # (1024,)
            "author_emb":       author_emb,          # (1024,)
            "noised_author_emb":noised_author_emb,  # (1024,)
        })

    torch.save(records, output_path)
    print(f"Saved {len(records)} embedded songs to {output_path}")
    return records

if __name__ == "__main__":
    preembed_songs(CSV_PATH, OUTPUT_PATH)