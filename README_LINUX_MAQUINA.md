# Setup — Linux amb dades des de la màquina UPC (`aulagpus`)

Variant del setup Linux quan **no** tens el `dades.zip` complet. Aquí el zip només porta dos fitxers grans (els que viuen al teu disc local) i la resta es baixa per `scp` des de `pe@aulagpus.fib.upc.edu`.

> **Quan usar aquesta guia**: només si tens accés SSH a `aulagpus`. Si no, usa [`README_LINUX.md`](README_LINUX.md) amb el `dades.zip` complet.

## Què porta el `dades.zip` "minimal"

Només 5.3 GB (en lloc dels 11 GB del complet):

```
dades_pack/
└── raw/
    ├── embedded_songs.parquet    # 5.2 GB
    └── augmented_songs.csv       # 120 MB
```

La resta (parquets de `embedded_songs_dataset/`, snapshot de lyrics, dumps de DB i export GA4) la baixaràs de la màquina al pas 6.

---

## 0. Prerequisits del sistema

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip build-essential curl unzip openssh-client
```

Node.js 20+:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

(Saltem Docker — usarem el binari natiu de Qdrant al pas 7.)

## 1. Clonar el repo

```bash
git clone https://github.com/gerardgrau/semantic-song-search-engine.git
cd semantic-song-search-engine
```

## 2. Entorn Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Variables d'entorn

```bash
cat > .env <<'EOF'
DB_HOST=aulagpus.fib.upc.edu
DB_PORT=60059
DB_USER=pe
DB_PASSWORD=bernatpudent
DB_NAME=viasona
EOF
```

## 4. Posar les dades base (`dades.zip` minimal)

```bash
mkdir -p app/backend/data/raw app/backend/data/processed ml/embeddings/embedded_songs_dataset ~/snapshots

unzip -o dades.zip
mv dades_pack/raw/* app/backend/data/raw/
rm -rf dades_pack/

ls -lh app/backend/data/raw/
# embedded_songs.parquet  (5.2 GB)
# augmented_songs.csv     (120 MB)
```

## 5. Configurar accés SSH a `aulagpus`

Si encara no en tens, demana les credencials (usuari `pe`, port SSH `60054`). Prova:

```bash
ssh -p 60054 pe@aulagpus.fib.upc.edu 'hostname && ls ~/semantic-song-search-engine/ml/embeddings/embedded_songs_dataset/ | head -5'
```

Has de veure el hostname de la màquina i alguns `batch_*.parquet`. Si demana password, prepara-te'l. (Recomanat: copia la teva clau pública amb `ssh-copy-id -p 60054 pe@aulagpus.fib.upc.edu` per estalviar-te repetir password.)

## 6. Baixar la resta de dades des de la màquina

### 6.1 Parquets de `embedded_songs_dataset/` (1.9 GB)

```bash
scp -P 60054 -r \
  pe@aulagpus.fib.upc.edu:~/semantic-song-search-engine/ml/embeddings/embedded_songs_dataset/ \
  ml/embeddings/
```

(Triga 1-3 min segons l'ample de banda.)

### 6.2 Dumps de la DB i export GA4 (115 MB)

```bash
scp -P 60054 \
  pe@aulagpus.fib.upc.edu:~/semantic-song-search-engine/app/backend/data/raw/{cancons,grups,noticies,entrances_exits}.csv \
  app/backend/data/raw/
```

> **Alternativa per als dumps de DB**: si vols recalcular `cancons/grups/noticies.csv` des de la BD en lloc de baixar-los, fes `python -m data_pipeline.step1_fetch_catalogue_csvs --force` (necessites estar a la xarxa UPC o tenir VPN). El `entrances_exits.csv` sempre ve per scp — és un export manual de Google Analytics.

### 6.3 Snapshot fresc de `songs_lyrics_chunks` (3.5 GB)

**A la màquina** (per SSH):

```bash
ssh -p 60054 pe@aulagpus.fib.upc.edu
# Dins de la màquina:
curl -X POST "http://localhost:6333/collections/songs_lyrics_chunks/snapshots"
# Apunta el nom del fitxer que retorna, p.ex.:
#   songs_lyrics_chunks-1234567890-2026-05-21-22-00-00.snapshot

# Si Qdrant corre a Docker, treu-lo al host:
docker cp qdrant_server:/qdrant/snapshots/songs_lyrics_chunks/ ~/lyrics_snapshot/
sudo chown pe:pe ~/lyrics_snapshot/*.snapshot
exit
```

**Local** — baixa el snapshot:

```bash
scp -P 60054 \
  'pe@aulagpus.fib.upc.edu:~/lyrics_snapshot/songs_lyrics_chunks-*.snapshot' \
  ~/snapshots/
```

(Triga 3-8 min segons xarxa.)

## 7. Aixecar Qdrant (binari natiu)

```bash
mkdir -p ~/qdrant && cd ~/qdrant
curl -L https://github.com/qdrant/qdrant/releases/download/v1.18.0/qdrant-x86_64-unknown-linux-gnu.tar.gz | tar -xz
cd ~
nohup ~/qdrant/qdrant > ~/qdrant.log 2>&1 &
```

Llançat des de `~`, l'storage queda a `~/storage/` i els snapshots a `~/snapshots/` — el path coincideix amb el del pas 6.3.

Comprova:

```bash
curl http://localhost:6333/
```

## 8. Restaurar `songs_lyrics_chunks` des del snapshot

```bash
SNAP=$(ls ~/snapshots/songs_lyrics_chunks-*.snapshot | head -1)
echo "Restaurant: $SNAP"

curl -X PUT "http://localhost:6333/collections/songs_lyrics_chunks/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d "{\"location\": \"file://$SNAP\"}"
```

(Triga 1-2 min — Qdrant reconstrueix l'índex HNSW de 743k punts.)

## 9. Reindexar `songs_qualitative`

```bash
cd ~/.../semantic-song-search-engine
source .venv/bin/activate
CUDA_VISIBLE_DEVICES="" python -m ml.embeddings.index_qdrant_docker --only-qualitative
```

(~2 min en CPU, llegeix els parquets que has baixat al pas 6.1.)

Comprova que tens **dues** col·leccions:

```bash
curl -s http://localhost:6333/collections | python3 -m json.tool
```

## 10. Generar parquets processed

```bash
python -m data_pipeline.execute_all
```

Step1 detecta els CSVs ja a `raw/` i salta. La resta de steps generen `top_5000_songs.csv`, `embedded_songs_top5000.parquet`, etc.

## 11. Arrencar el backend

```bash
uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

> **Primer arrencament**: descarrega `BAAI/bge-m3` (~2.3 GB) i el cross-encoder (~120 MB). 5-10 min la primera vegada.

## 12. Arrencar el frontend

Segona terminal:

```bash
cd app/frontend
npm install
npm run dev
```

Obre <http://localhost:3000>.

---

## Resum del flux de baixada

| Què | D'on | Mida | Comanda |
|---|---|---|---|
| `embedded_songs.parquet` | `dades.zip` (local) | 5.2 GB | `unzip` |
| `augmented_songs.csv` | `dades.zip` (local) | 120 MB | `unzip` |
| `embedded_songs_dataset/` | `aulagpus`, `~/semantic-song-search-engine/ml/embeddings/` | 1.9 GB | `scp -r` |
| `cancons/grups/noticies/entrances_exits.csv` | `aulagpus`, `~/semantic-song-search-engine/app/backend/data/raw/` | 115 MB | `scp` |
| `songs_lyrics_chunks-*.snapshot` | `aulagpus`, generat amb `curl POST` | 3.5 GB | `scp` |

Total xarxa: ~5.6 GB. Total disc final: ~11 GB.

## Troubleshooting

- **`ssh: connect to host … port 60054: Connection refused`** → el port SSH ha canviat o no estàs autoritzat. Demana credencials actuals.
- **`scp: No such file or directory`** durant `embedded_songs_dataset/` → el path del repo a la màquina pot ser diferent. Connecta't per SSH i fes `find ~ -name 'batch_*.parquet' -path '*/embedded_songs_dataset/*' | head -3` per localitzar-lo.
- **Qdrant restore retorna `{"status":"error",…}`** → el path del `file://` ha de ser **absolut**. Comprova amb `realpath ~/snapshots/*.snapshot`.
- **`docker: command not found`** a la màquina → potser corre Qdrant com a binari natiu. En aquest cas el snapshot ja és a `~/snapshots/songs_lyrics_chunks/` sense necessitat de `docker cp`.
