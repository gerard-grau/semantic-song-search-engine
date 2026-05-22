# Setup — Linux (natiu o WSL2)

Guia per a **Ubuntu / Debian natiu** i per a **Windows 10/11 amb WSL2** (Ubuntu). Els passos comuns són els mateixos: el que canvia està marcat com a *WSL-only* o *natiu-only*. Si vas amb una altra distro (Arch, Fedora, …), substitueix `apt` pel teu gestor — la resta funciona igual.

> **Si fas servir WSL2**: treballa **dins** del filesystem Linux (`~`). Si poses el repo a `/mnt/c/...`, el parquet de 5 GB triga ~10× més per llegir-se.

---

## 0. *WSL-only* — Activar WSL2 + Ubuntu

> Salta aquest pas si ja tens Ubuntu/Debian natiu o el WSL ja instal·lat.

A **PowerShell com a Administrador** (Windows):

```powershell
wsl --install -d Ubuntu
wsl --set-default-version 2
```

Reinicia Windows si ho demana. Obre `Ubuntu` des del menú d'inici i crea l'usuari Linux. La resta de la guia s'executa **dins** d'aquesta terminal Ubuntu.

## 1. Prerequisits del sistema

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip build-essential curl unzip
```

Node.js 20+:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

> **Docker no és necessari.** El pas 6 té dues opcions per aixecar Qdrant: el **binari natiu** (recomanat — un sol `tar -xz`, sense daemon) o Docker. Si no penses fer servir Docker per res més, salta aquesta secció.

<details>
<summary>Instal·lar Docker (només si el vols)</summary>

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo service docker start
newgrp docker
```

**WSL-only**: si prefereixes Docker Desktop a Windows, instal·la-l i activa la integració amb WSL2 a `Settings → Resources → WSL Integration`.

</details>

## 2. Clonar el repo

```bash
git clone https://github.com/gerardgrau/semantic-song-search-engine.git
cd semantic-song-search-engine
```

## 3. Entorn Python

```bash
python3 -m venv .venv
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

Copia `dades.zip` a l'arrel del repo i descomprimeix:

```bash
mkdir -p app/backend/data/raw app/backend/data/processed ml/embeddings/embedded_songs_dataset ~/snapshots

unzip -o dades.zip

mv dades_pack/raw/* app/backend/data/raw/
mv dades_pack/embedded_songs_dataset/* ml/embeddings/embedded_songs_dataset/
mv dades_pack/snapshots/*.snapshot ~/snapshots/

rm -rf dades_pack/
```

> **WSL-only**: per copiar `dades.zip` des de Windows, obre l'explorador a `\\wsl$\Ubuntu\home\<usuari>\` i navega fins a la carpeta del repo. **No** deixis ni el zip ni el descomprimit a `/mnt/c/...`: tot ha de viure dins del fs Linux per evitar el penal de I/O.

## 6. Aixecar Qdrant

**Tria una de les dues opcions** (no totes dues). La A és la recomanada si no tens Docker.

### Opció A — Binari natiu (recomanat, sense Docker)

```bash
mkdir -p ~/qdrant && cd ~/qdrant
curl -L https://github.com/qdrant/qdrant/releases/download/v1.18.0/qdrant-x86_64-unknown-linux-gnu.tar.gz | tar -xz
cd ~
nohup ~/qdrant/qdrant > ~/qdrant.log 2>&1 &
```

Qdrant queda escoltant a `localhost:6333` i persisteix les dades a `~/storage/`. Per parar-lo: `pkill -f ~/qdrant/qdrant`.

<details>
<summary><strong>Opció B — Docker</strong> (només si ja tens Docker instal·lat)</summary>

```bash
docker run -d --name qdrant_server \
  -p 6333:6333 -p 6334:6334 \
  -v "$HOME/qdrant_storage:/qdrant/storage" \
  -v "$HOME/snapshots:/qdrant/snapshots" \
  qdrant/qdrant:v1.18.0
```

</details>

### Comprovació (qualsevol opció)

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

**Natiu**:

```bash
uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

**WSL-only**: usa `--host 0.0.0.0` perquè el navegador de Windows pugui accedir-hi (WSL2 fa el port-forwarding automàticament):

```bash
uvicorn app.backend.api.main:app --host 0.0.0.0 --port 8000
```

> **Primer arrencament**: descarrega `BAAI/bge-m3` (~2.3 GB) i el cross-encoder (~120 MB). Pot trigar 5-10 min la primera vegada.

## 11. Arrencar el frontend

Segona terminal, des de l'arrel del repo:

```bash
cd app/frontend
npm install
npm run dev          # natiu
npm run dev -- --host  # WSL — necessari perquè Windows hi accedeixi
```

Obre <http://localhost:3000>.

---

## Notes específiques de WSL2

- Si el navegador de Windows no veu `localhost:8000` o `:3000`, executa `wsl --shutdown` a PowerShell i reobre Ubuntu.
- El parquet de 5 GB **ha de viure dins del fs Linux** (`~/.../semantic-song-search-engine/`), no a `/mnt/c/...`.
- Si tens GPU NVIDIA, instal·la els CUDA toolkits oficials per a WSL2; bge-m3 corre en CPU per defecte.

## Notes per a Linux natiu

- Per defecte `uvicorn` només escolta a `127.0.0.1`. Si vols accedir-hi des d'una altra màquina de la xarxa, usa `--host 0.0.0.0` i obre el port al `ufw`/firewall.
- Si tens GPU NVIDIA i vols accelerar la inferència, instal·la els drivers CUDA del teu vendor (Ubuntu: `sudo apt install nvidia-cuda-toolkit`) i treu la variable `CUDA_VISIBLE_DEVICES=""` quan executis pas 8 o el backend.
- Si fas servir Wayland o un escriptori sense `nohup`-friendly shells, considera llançar Qdrant amb `systemd --user` o `tmux` enlloc de `nohup … &`.
