from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.decomposition import PCA
from sklearn.manifold import MDS, TSNE
from sklearn.preprocessing import StandardScaler


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
DATA_DIR = BACKEND_DIR / "data"


def data_path(filename):
    return DATA_DIR / filename


def _to_embedding_matrix(series):
    embeddings = []

    for value in series:
        if isinstance(value, str):
            value = value.strip()

            if value.startswith("[") and value.endswith("]"):
                value = np.fromstring(value.strip("[]"), sep=",")
            else:
                raise ValueError("Embedding is stored as a string but is not a valid list.")

        embeddings.append(np.array(value, dtype=np.float32))

    return np.vstack(embeddings)


def generate_2D(
    input_file="embedded_songs.parquet",
    output_file="embedded_songs_2d.parquet",
    method="pca",
    scale=True,
    random_state=42,
    limit=None,
):
    input_path = data_path(input_file)
    output_path = data_path(output_file)

    table = pq.read_table(
        input_path,
        columns=["id_lyrics", "embedded_lyrics"],
    )

    df = table.to_pandas()

    if limit is not None:
        df = df.head(limit)

    if df.empty:
        raise ValueError("The input embedding file is empty.")

    ids = df["id_lyrics"].to_numpy()
    X = _to_embedding_matrix(df["embedded_lyrics"])

    if scale:
        X = StandardScaler().fit_transform(X)

    method = method.lower()

    if method == "pca":
        projector = PCA(n_components=2, random_state=random_state)
        X_2d = projector.fit_transform(X)

    elif method == "mds":
        projector = MDS(
            n_components=2,
            random_state=random_state,
            n_init=1,
            max_iter=300,
            normalized_stress="auto",
        )
        X_2d = projector.fit_transform(X)

    elif method == "tsne":
        projector = TSNE(
            n_components=2,
            random_state=random_state,
            perplexity=30,
            init="pca",
            learning_rate="auto",
        )
        X_2d = projector.fit_transform(X)

    else:
        raise ValueError(
            f"Unknown method: {method}. Use one of: 'pca', 'mds', 'tsne'."
        )

    result = pd.DataFrame(
        {
            "id_lyrics": ids,
            "x": X_2d[:, 0],
            "y": X_2d[:, 1],
            "method": method,
        }
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_path, index=False)

    return {
        "rows": len(result),
        "method": method,
        "output_file": str(output_path),
    }


if __name__ == "__main__":
    result = generate_2D(method="pca")
    print(result)