# Setup — Windows amb WSL2 (Ubuntu)

Guia per a Windows 11 / 10 amb WSL2. Tot el codi corre dins d'Ubuntu — Windows només munta el filesystem.

> **Important**: treballa **dins** del filesystem Linux (`~`). Si poses el repo a `/mnt/c/...`, el parquet de 5 GB triga 10× més per llegir-se.

## 0. Activar WSL2 + Ubuntu

A **PowerShell com a Administrador**:

```powershell
wsl --install -d Ubuntu
wsl --set-default-version 2
```

Reinicia Windows si ho demana. Obre `Ubuntu` des del menú d'inici i crea l'usuari Linux.

## 1. Prerequisits dins d'Ubuntu (WSL)

```bash
sudo apt update
sudo apt install -y git python3.11 python3.11-venv python3-pip build-essential curl unzip
```

Node.js 20+:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Docker dins de WSL2 **o** descarrega el binari natiu de Qdrant (pas 5).

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo service docker start
newgrp docker
```

> Si prefereixes Docker Desktop, instal·la-l a Windows i activa la integració amb WSL2 a `Settings → Resources → WSL Integration`.

## 2. Clonar el repo

```bash
cd ~
git clone <URL_DEL_REPO> semantic-song-search-engine
cd semantic-song-search-engine
```

## 3. Entorn Python

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Variables d'entorn

```bash
cat > .env <<'EOF'
DB_HOST=aulagpus.fib.upc.edu
DB_PORT=60059
DB_USER=pe
DB_PASSWORD=bernatpudent
DB_NAME=viasona
EOF
```

## 5. Posar les dades base

Copia `dades.zip` al repo. Des de Windows pots fer-ho amb l'explorador anant a `\\wsl$\Ubuntu\home\<usuari>\semantic-song-search-engine\`. Després:

```bash
mkdir -p app/backend/data/raw app/backend/data/processed ml/embeddings/embedded_songs_dataset ~/snapshots

unzip -o dades.zip

mv dades_pack/raw/* app/backend/data/raw/
mv dades_pack/embedded_songs_dataset/* ml/embeddings/embedded_songs_dataset/
mv dades_pack/snapshots/*.snapshot ~/snapshots/

rm -rf dades_pack/
```

## 6. Aixecar Qdrant

### Opció A — Binari natiu (recomanat)

```bash
mkdir -p ~/qdrant && cd ~/qdrant
curl -L https://github.com/qdrant/qdrant/releases/download/v1.18.0/qdrant-x86_64-unknown-linux-gnu.tar.gz | tar -xz
cd ~
nohup ~/qdrant/qdrant > ~/qdrant.log 2>&1 &
```

### Opció B — Docker

```bash
docker run -d --name qdrant_server \
  -p 6333:6333 -p 6334:6334 \
  -v "$HOME/qdrant_storage:/qdrant/storage" \
  -v "$HOME/snapshots:/qdrant/snapshots" \
  qdrant/qdrant:v1.18.0
```

Comprova:

```bash
curl http://localhost:6333/
```

## 7. Restaurar `songs_lyrics_chunks` des del snapshot

```bash
SNAP=$(ls ~/snapshots/songs_lyrics_chunks-*.snapshot | head -1)

curl -X PUT "http://localhost:6333/collections/songs_lyrics_chunks/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d "{\"location\": \"file://$SNAP\"}"
```

## 8. Reindexar `songs_qualitative`

> Torna a l'arrel del repo si encara estàs a `~` del pas 6 (`cd ~/.../semantic-song-search-engine`).

```bash
source .venv/bin/activate
CUDA_VISIBLE_DEVICES="" python -m ml.embeddings.index_qdrant_docker --only-qualitative
```

Comprova que tens **dues** col·leccions:

```bash
curl -s http://localhost:6333/collections | python3 -m json.tool
```

## 9. Generar processed

```bash
python -m data_pipeline.execute_all
```

## 10. Arrencar el backend

```bash
uvicorn app.backend.api.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` permet que el navegador de Windows hi accedeixi (WSL2 fa port-forwarding automàtic).

> **Primer arrencament**: descarrega `BAAI/bge-m3` (~2.3 GB) i el cross-encoder (~120 MB). Pot trigar 5-10 min la primera vegada.

## 11. Arrencar el frontend

Segona terminal WSL:

```bash
cd ~/semantic-song-search-engine/app/frontend
npm install
npm run dev -- --host
```

Obre des de Windows: <http://localhost:5173>.

## Notes específiques de WSL2

- Si el navegador Windows no veu `localhost:8000` o `:5173`, executa `wsl --shutdown` a PowerShell i reobre Ubuntu.
- El parquet de 5 GB **ha de viure dins del fs Linux** (`~/semantic-song-search-engine/...`), no a `/mnt/c/...`.
- Si tens GPU NVIDIA, instal·la els CUDA toolkits oficials per a WSL2; bge-m3 corre en CPU per defecte.
