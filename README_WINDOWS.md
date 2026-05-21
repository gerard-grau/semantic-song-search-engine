# Setup — Windows natiu (sense WSL)

Guia per a Windows 10/11 amb Python instal·lat al sistema. Tot el codi corre a PowerShell. Si t'és més còmode, mira [`README_WSL.md`](README_WSL.md) — és més robust per al parquet de 5 GB.

## 0. Prerequisits

Instal·la les eines bàsiques (com a Administrador):

1. **Git for Windows** — <https://git-scm.com/download/win>
2. **Python 3.11** — <https://www.python.org/downloads/>  ✅ "Add Python to PATH"
3. **Node.js 20 LTS** — <https://nodejs.org/>
4. **Docker Desktop** — <https://www.docker.com/products/docker-desktop/>
5. **7-Zip** — <https://www.7-zip.org/> (`Expand-Archive` no gestiona bé arxius de >4 GB)

Reinicia el terminal després de cada instal·lador.

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

Si PowerShell bloqueja l'activació:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 3. Variables d'entorn

Crea `.env` a l'arrel amb el bloc de notes (guardat **sense extensió** `.txt`):

```
DB_HOST=aulagpus.fib.upc.edu
DB_PORT=60059
DB_USER=pe
DB_PASSWORD=bernatpudent
DB_NAME=viasona
```

## 4. Posar les dades base

Posa `dades.zip` a l'arrel del repo. Des de PowerShell, amb 7-Zip (necessari per a arxius >4 GB; `Expand-Archive` natiu falla):

```powershell
& "C:\Program Files\7-Zip\7z.exe" x .\dades.zip

mkdir app\backend\data\raw -Force | Out-Null
mkdir app\backend\data\processed -Force | Out-Null
mkdir ml\embeddings\embedded_songs_dataset -Force | Out-Null
mkdir $HOME\qdrant_snapshots -Force | Out-Null

Move-Item .\dades_pack\raw\* .\app\backend\data\raw\ -Force
Move-Item .\dades_pack\embedded_songs_dataset\* .\ml\embeddings\embedded_songs_dataset\ -Force
Move-Item .\dades_pack\snapshots\*.snapshot $HOME\qdrant_snapshots\ -Force

Remove-Item .\dades_pack -Recurse -Force
```

## 5. Aixecar Qdrant amb Docker Desktop

Assegura't que Docker Desktop està obert. Llavors:

```powershell
docker run -d `
  --name qdrant_server `
  -p 6333:6333 -p 6334:6334 `
  -v "${HOME}\qdrant_storage:/qdrant/storage" `
  -v "${HOME}\qdrant_snapshots:/qdrant/snapshots" `
  qdrant/qdrant:v1.18.0
```

Comprova:

```powershell
curl.exe http://localhost:6333/
```

(`curl.exe` és imprescindible — `curl` a PowerShell és un àlies d'`Invoke-WebRequest`.)

## 6. Restaurar `songs_lyrics_chunks`

Identifica el fitxer i el seu nom dins del contenidor Docker:

```powershell
$snapName = (Get-ChildItem $HOME\qdrant_snapshots\songs_lyrics_chunks-*.snapshot | Select-Object -First 1).Name
echo $snapName

curl.exe -X PUT "http://localhost:6333/collections/songs_lyrics_chunks/snapshots/recover" `
  -H "Content-Type: application/json" `
  -d "{\""location\"": \""file:///qdrant/snapshots/$snapName\""}"
```

(El path `file:///qdrant/snapshots/...` és **dins del contenidor**, no del host.)

## 7. Reindexar `songs_qualitative`

```powershell
$env:CUDA_VISIBLE_DEVICES = ""
python -m ml.embeddings.index_qdrant_docker --only-qualitative
```

Comprova:

```powershell
curl.exe http://localhost:6333/collections
```

## 8. Generar processed

```powershell
python -m data_pipeline.execute_all
```

## 9. Arrencar el backend

```powershell
uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

> **Primer arrencament**: descarrega `BAAI/bge-m3` (~2.3 GB) i el cross-encoder (~120 MB). 5-10 min.

## 10. Arrencar el frontend

En una **segona** PowerShell, des de l'arrel del repo:

```powershell
cd app\frontend
npm install
npm run dev
```

Obre <http://localhost:5173>.

## Problemes coneguts amb Windows natiu

- **`Expand-Archive` falla** amb `dades.zip` → usa 7-Zip (és per això que és prerequisit).
- **`torch`/`transformers`** poden trigar a compilar. Si vols GPU, instal·la la wheel CUDA específica: `pip install torch --index-url https://download.pytorch.org/whl/cu121`.
- Si **Docker Desktop no està actiu**, `docker run` falla silenciosament.
- Els paths amb `\` són equivalents als `/` Linux per als scripts Python; el codi del repo els accepta tots dos.
