# Guia d'execució — Linux / Mac

## Prerequisits

- **Python 3.11+**
- **Node.js 18+** (via `nvm` o el gestor de paquets del sistema)
- **pip** i **npm**

## Pas a pas

### 1. Clonar el repositori

```bash
git clone <url-del-repo>
cd semantic-song-search-engine
```

### 2. Entorn virtual de Python + dependències

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Arrencar el backend (Terminal 1)

```bash
uvicorn app.backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

El backend estarà a `http://127.0.0.1:8000`. Swagger UI a `http://127.0.0.1:8000/docs`.

### 4. Instal·lar dependències frontend (Terminal 2)

```bash
cd app/frontend
npm install
```

### 5. Arrencar el frontend

```bash
npm run dev
```

El frontend estarà a `http://localhost:3000`.

### 6. Obrir l'aplicació

Ves a **http://localhost:3000** al navegador.

## Instal·lació de Node.js amb nvm (opcional)

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 22
nvm use 22
```

## Resolució de problemes

| Problema | Solució |
|---|---|
| `ImportError: Sentinel` | `pip install -U typing_extensions` |
| `scikit-learn` no s'instal·la | `pip install scikit-learn` manualment |
| Port 8000 ja en ús | `uvicorn ... --port 8001` i actualitza `vite.config.js` |
