# Setup — Linux

Guia pas a pas. Assumeix una distribució recent (Ubuntu 22.04+ o equivalent) amb permisos `sudo`. Tot el text entre `…` cal substituir-lo.

## 0. Prerequisits del sistema

```bash
sudo apt update
sudo apt install -y git python3.11 python3.11-venv python3-pip build-essential curl
```

Instal·la Node.js 20+:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Instal·la Docker (per Qdrant):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker     # rellegeix grups sense tancar sessió
```

## 1. Clonar el repo

```bash
git clone <URL_DEL_REPO> semantic-song-search-engine
cd semantic-song-search-engine
```

## 2. Entorn Python

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Variables d'entorn

Crea `.env` a l'arrel amb les credencials de la BD de Viasona:

```bash
cat > .env <<'EOF'
DB_HOST=aulagpus.fib.upc.edu
DB_PORT=60059
DB_USER=pe
DB_PASSWORD=bernatpudent
DB_NAME=viasona
EOF
```

## 4. Posar les dades base

Copia `dades.zip` a l'arrel del repo i descomprimeix:

```bash
mkdir -p app/backend/data/raw app/backend/data/processed
unzip -o dades.zip -d .
mv embedded_songs.parquet app/backend/data/raw/
mv augmented_songs.csv    app/backend/data/raw/
mv entrances_exits.csv    app/backend/data/raw/
# El volum de Qdrant queda a ./qdrant_storage/
```

## 5. Aixecar Qdrant amb el volum pre-poblat

```bash
docker run -d \
  --name qdrant_server \
  -p 6333:6333 -p 6334:6334 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage" \
  qdrant/qdrant
```

Comprova que respon:

```bash
curl http://localhost:6333/collections
```

Hi has de veure `songs_qualitative` i `songs_lyrics_chunks`.

## 6. Generar la resta d'artefactes (parquets)

```bash
python -m data_pipeline.execute_all
```

Genera `cancons.csv`, `grups.csv`, `noticies.csv` (de la BD) i tots els parquets dins de `app/backend/data/processed/`.

## 7. Arrencar el backend

```bash
uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

Comprova:

```bash
curl http://localhost:8000/
```

## 8. Arrencar el frontend

En una **segona terminal**, des de l'arrel del repo:

```bash
cd app/frontend
npm install
npm run dev
```

Obre <http://localhost:5173>.
