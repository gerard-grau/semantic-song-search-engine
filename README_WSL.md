# Setup — Windows amb WSL2 (Ubuntu)

Guia per a Windows 11 / 10 amb WSL2. Tot el codi corre dins d'Ubuntu — Windows només munta el filesystem.

## 0. Activar WSL2 + Ubuntu

A PowerShell com a Administrador:

```powershell
wsl --install -d Ubuntu
wsl --set-default-version 2
```

Reinicia Windows quan ho demani. Obre `Ubuntu` des del menú d'inici i crea l'usuari Linux.

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

Docker dins de WSL2 (mètode oficial sense Docker Desktop):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo service docker start
newgrp docker
```

> Si prefereixes Docker Desktop, instal·la-l a Windows i activa la integració amb WSL2 a `Settings → Resources → WSL Integration`.

## 2. Clonar el repo

Treballa **dins** del filesystem de Linux (mai sota `/mnt/c/...` per rendiment del parquet de 5 GB):

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

Copia `dades.zip` al repo (des de Windows pots fer-ho a `\\wsl$\Ubuntu\home\<usuari>\semantic-song-search-engine`) i descomprimeix:

```bash
mkdir -p app/backend/data/raw app/backend/data/processed
unzip -o dades.zip -d .
mv embedded_songs.parquet app/backend/data/raw/
mv augmented_songs.csv    app/backend/data/raw/
mv entrances_exits.csv    app/backend/data/raw/
```

## 6. Aixecar Qdrant amb el volum pre-poblat

```bash
docker run -d \
  --name qdrant_server \
  -p 6333:6333 -p 6334:6334 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage" \
  qdrant/qdrant
```

Comprova:

```bash
curl http://localhost:6333/collections
```

## 7. Generar la resta d'artefactes

```bash
python -m data_pipeline.execute_all
```

## 8. Arrencar el backend

```bash
uvicorn app.backend.api.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` permet que el navegador de Windows hi accedeixi (WSL2 fa port forwarding automàtic).

## 9. Arrencar el frontend

Segona terminal WSL:

```bash
cd ~/semantic-song-search-engine/app/frontend
npm install
npm run dev -- --host
```

Obre des de Windows: <http://localhost:5173>.

## Notes específiques de WSL2

- Si el navegador Windows no veu `localhost:8000` o `:5173`, executa `wsl --shutdown` a PowerShell i reobre l'Ubuntu.
- El parquet de 5 GB ha de viure dins del fs Linux (`~`), no a `/mnt/c/...`, o la I/O serà ~10× més lenta.
- Si tens GPU NVIDIA, instal·la els CUDA toolkits oficials per a WSL2; bge-m3 corre en CPU per defecte si no troba CUDA.
