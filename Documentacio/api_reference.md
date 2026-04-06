# Referència de l'API

Base URL: `http://127.0.0.1:8000`

Documentació interactiva (Swagger): `http://127.0.0.1:8000/docs`

## Endpoints

### `GET /`

Health check.

```bash
curl http://127.0.0.1:8000/
```

Resposta:
```json
{"status": "ok", "message": "Semantic Song Search Engine API v0.2"}
```

---

### `GET /api/songs`

Retorna totes les cançons amb projeccions t-SNE cached.
S'utilitza per la càrrega inicial i quan l'usuari prem "Reset".

```bash
curl http://127.0.0.1:8000/api/songs
```

Resposta:
```json
{
  "songs": [
    {
      "id": 1,
      "title": "Boig per tu",
      "artist": "Sau",
      "album": "Boig per tu",
      "genre": "pop",
      "year": 1990,
      "lyrics_snippet": "Estic boig per tu, no ho puc evitar...",
      "score": 0.0
    }
  ],
  "projections_2d": [
    { "id": 1, "x": 12.34, "y": -5.67, "title": "Boig per tu", "artist": "Sau", "genre": "pop" }
  ],
  "projections_3d": [
    { "id": 1, "x": 3.21, "y": -1.45, "z": 7.89, "title": "Boig per tu", "artist": "Sau", "genre": "pop" }
  ],
  "total": 50
}
```

---

### `POST /api/filter`

Filtratge progressiu. Rep una consulta i opcionalment els IDs de cançons actuals, retorna el subconjunt filtrat amb noves projeccions t-SNE.

```bash
# Primera cerca (des de totes les cançons)
curl -X POST http://127.0.0.1:8000/api/filter \
  -H "Content-Type: application/json" \
  -d '{"query": "rock", "song_ids": null}'

# Segona cerca (filtrant només les supervivents)
curl -X POST http://127.0.0.1:8000/api/filter \
  -H "Content-Type: application/json" \
  -d '{"query": "endavant", "song_ids": [11, 14, 16, 18, 19]}'
```

Cos de la petició:
```json
{
  "query": "string (obligatori)",
  "song_ids": [1, 2, 3] | null
}
```

- `song_ids = null` → filtra des de totes les cançons
- `song_ids = [...]` → filtra només les cançons amb aquests IDs

Resposta:
```json
{
  "songs": [
    { "id": 16, "title": "Sempre endavant", "artist": "Brams", "score": 0.92, ... }
  ],
  "projections_2d": [...],
  "projections_3d": [...],
  "total_remaining": 4,
  "message": null | "Explora les 4 cançons per tu"
}
```

`message` apareix quan `total_remaining ≤ 5`.

La funció de filtratge **mai retorna 0 cançons** (mínim 1).

---

### `GET /api/songs/{song_id}`

Retorna tots els detalls d'una cançó concreta (inclou lletra completa i URL).

```bash
curl http://127.0.0.1:8000/api/songs/1
```

Resposta:
```json
{
  "id": 1,
  "title": "Boig per tu",
  "artist": "Sau",
  "album": "Boig per tu",
  "genre": "pop",
  "year": 1990,
  "lyrics_snippet": "Estic boig per tu, no ho puc evitar...",
  "full_lyrics": "Primer vers de la cançó...\n\nSegon vers...",
  "url": "https://www.viasona.cat/grup/sau/boig-per-tu/boig-per-tu",
  "duration": "3:45",
  "language": "Català"
}
```

---

## Ús independent de l'API

L'API es pot utilitzar independentment del frontend. Exemples:

```python
import requests

BASE = "http://127.0.0.1:8000/api"

# 1. Carregar totes les cançons
all_data = requests.get(f"{BASE}/songs").json()
print(f"Total: {all_data['total']} cançons")

# 2. Primera cerca
r = requests.post(f"{BASE}/filter", json={"query": "amor", "song_ids": None})
result = r.json()
surviving_ids = [s["id"] for s in result["songs"]]
print(f"Supervivents: {result['total_remaining']}")

# 3. Segona cerca (progressiva)
r = requests.post(f"{BASE}/filter", json={"query": "nit", "song_ids": surviving_ids})
result = r.json()
print(f"Supervivents: {result['total_remaining']}")
if result["message"]:
    print(result["message"])

# 4. Detall d'una cançó
song = requests.get(f"{BASE}/songs/1").json()
print(f"{song['title']} — {song['artist']}")
print(song["full_lyrics"])
```
