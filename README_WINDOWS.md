# Setup — Windows natiu (sense WSL)

Guia per a Windows 10/11 amb Python instal·lat al sistema. Tot el codi corre a Powershell. Si t'és més còmode, mira [`README_WSL.md`](README_WSL.md) (és més robust).

## 0. Prerequisits

Instal·la les eines bàsiques (administrador):

1. **Git for Windows** — <https://git-scm.com/download/win>
2. **Python 3.11** — <https://www.python.org/downloads/> ✅ "Add Python to PATH"
3. **Node.js 20 LTS** — <https://nodejs.org/>
4. **Docker Desktop** — <https://www.docker.com/products/docker-desktop/> (necessari per Qdrant)
5. Reinicia el terminal després de cada instal·lador.

Obre **PowerShell** (no CMD) per a la resta dels passos.

## 1. Clonar el repo

```powershell
cd $HOME
git clone <URL_DEL_REPO> semantic-song-search-engine
cd semantic-song-search-engine
```

## 2. Entorn Python

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell bloqueja l'activació, executa una vegada com a administrador:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 3. Variables d'entorn

Crea `.env` a l'arrel del repo amb aquest contingut:

```
DB_HOST=aulagpus.fib.upc.edu
DB_PORT=60059
DB_USER=pe
DB_PASSWORD=bernatpudent
DB_NAME=viasona
```

(Pots fer-ho amb el bloc de notes, **guardat com `.env`** sense extensió `.txt`.)

## 4. Posar les dades base

Posa `dades.zip` a l'arrel del repo i descomprimeix. Des de PowerShell:

```powershell
mkdir app\backend\data\raw -Force | Out-Null
mkdir app\backend\data\processed -Force | Out-Null
Expand-Archive -Path .\dades.zip -DestinationPath . -Force
Move-Item .\embedded_songs.parquet .\app\backend\data\raw\ -Force
Move-Item .\augmented_songs.csv    .\app\backend\data\raw\ -Force
Move-Item .\entrances_exits.csv    .\app\backend\data\raw\ -Force
```

## 5. Aixecar Qdrant amb el volum pre-poblat

Assegura't que Docker Desktop està obert. Llavors:

```powershell
docker run -d `
  --name qdrant_server `
  -p 6333:6333 -p 6334:6334 `
  -v "${PWD}\qdrant_storage:/qdrant/storage" `
  qdrant/qdrant
```

Comprova:

```powershell
curl.exe http://localhost:6333/collections
```

(`curl.exe` és imprescindible perquè a Windows `curl` és un àlies d'`Invoke-WebRequest`.)

## 6. Generar la resta d'artefactes

```powershell
python -m data_pipeline.execute_all
```

## 7. Arrencar el backend

```powershell
uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

## 8. Arrencar el frontend

En una **segona** PowerShell, des de l'arrel del repo:

```powershell
cd app\frontend
npm install
npm run dev
```

Obre <http://localhost:5173>.

## Problemes coneguts amb Windows natiu

- **`torch`/`transformers`** poden trigar a compilar. Si vols GPU, instal·la la wheel CUDA específica: `pip install torch --index-url https://download.pytorch.org/whl/cu121`.
- Si Docker Desktop no està actiu, `docker run` fallarà silenciosament des de PowerShell.
- Tots els paths amb `\` són equivalents als `/` de Linux a les rutes Python; els scripts del repo els generen tots dos.
- Si tens problemes per executar `python -m data_pipeline.execute_all`, comprova que `(venv) PS C:\...\>` apareix al prompt (vol dir que el venv està actiu).
