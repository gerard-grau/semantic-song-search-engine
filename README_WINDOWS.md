# Guia d'execució — Windows

## Prerequisits

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **pip** (inclòs amb Python)
- **npm** (inclòs amb Node.js)

## Pas a pas

### 1. Clonar el repositori

```powershell
git clone <url-del-repo>
cd semantic-song-search-engine
```

### 2. Entorn virtual de Python + dependències

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Arrencar el backend (Terminal 1)

```powershell
uvicorn app.backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

El backend estarà a `http://127.0.0.1:8000`. Documentació interactiva a `http://127.0.0.1:8000/docs`.

### 4. Instal·lar dependències frontend (Terminal 2)

```powershell
cd app\frontend
npm install
```

### 5. Arrencar el frontend

```powershell
npm run dev
```

El frontend estarà a `http://localhost:3000`.

### 6. Obrir l'aplicació

Ves a **http://localhost:3000** al navegador.

## Nota per usuaris de WSL

Si utilitzes WSL (Windows Subsystem for Linux) i tens problemes amb `npm run dev` (permission denied), utilitza:

```bash
node.exe node_modules/vite/bin/vite.js
```

O instal·la Node.js nativament dins de WSL:

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

## Resolució de problemes

| Problema | Solució |
|---|---|
| `ImportError: cannot import name 'Sentinel' from 'typing_extensions'` | `pip install -U typing_extensions` |
| `permission denied` al executar `npm run dev` des de WSL | Veure la nota de WSL a dalt |
| El frontend no es connecta al backend | Assegura't que el backend corre al port 8000 |
