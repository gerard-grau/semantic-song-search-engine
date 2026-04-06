# Filtratge Progressiu

## Concepte

L'usuari cerca repetidament i cada cerca redueix el conjunt de cançons disponibles. Això simula un procés de "descoberta" on l'usuari refina els seus criteris fins trobar les cançons que busca.

## Flux complet

```
Estat inicial: 50 cançons → t-SNE calculat i cachetat

Cerca 1: "rock"
  → Backend rep query="rock", song_ids=null (totes)
  → filter_embeddings("rock", 50 cançons) → 11 supervivents
  → compute_tsne_2d(11 cançons) → noves coordenades 2D
  → compute_tsne_3d(11 cançons) → noves coordenades 3D
  → Frontend mostra 11 cançons, visualització actualitzada

Cerca 2: "endavant" (des de les 11 supervivents)
  → Backend rep query="endavant", song_ids=[11,14,16,18,...]
  → filter_embeddings("endavant", 11 cançons) → 4 supervivents
  → t-SNE recalculat per les 4
  → message: "Explora les 4 cançons per tu"

Cerca 3: "brams"
  → Backend rep query="brams", song_ids=[16,18,19,11]
  → filter_embeddings("brams", 4 cançons) → 2 supervivents
  → message: "Explora les 2 cançons per tu"
  → Visualització semi-transparent

Reset:
  → Frontend crida GET /api/songs
  → Recupera les 50 cançons + t-SNE cached (instantani)
  → songIds torna a null
```

## Frontend (App.jsx)

L'estat `songIds` controla quines cançons estan "vives":

```
songIds = null        → Totes les cançons (estat inicial i post-reset)
songIds = [1,3,5,...] → Només les supervivents
```

Cada cerca envia `songIds` al backend. El backend filtra només aquell subconjunt.

## Backend (filter_embeddings)

### Implementació mock actual

```python
def filter_embeddings(query_text, songs):
    # 1. Substring match (case-insensitive) en títol/artista/lletra/gènere
    # 2. Matches → score 0.70-1.00 → es mantenen TOTS
    # 3. No-matches → score 0.05-0.40 → es manté ~30% aleatori
    # 4. Mai retorna 0 → si tot es filtraria, es manté el millor
    # 5. Retorna ordenat per score descendent
```

Això fa que:
- Cada cerca redueixi el conjunt (~30-70% sobreviu)
- 2-4 cerques arriben a ≤5 cançons
- Mai queda buit

### Implementació real (a substituir)

```python
def filter_embeddings(query_text, songs):
    # 1. query_emb = model.encode(f"query: {query_text}")
    # 2. Per cada cançó: score = cosine_sim(query_emb, song.embedding)
    # 3. threshold = adaptive_threshold(scores)  # ex: percentil 60
    # 4. survivors = [s for s in songs if s.score >= threshold]
    # 5. if not survivors: survivors = [max(songs, key=score)]
    # 6. return sorted(survivors, key=score, reverse=True)
```

## Per què recalcular t-SNE?

Quan filtrem, el subconjunt de cançons canvia. t-SNE és un algorisme que considera les relacions entre TOTS els punts del conjunt. Amb menys punts, les relacions canvien:

- Amb 50 cançons: folk i pop poden estar a prop
- Amb 5 cançons de gèneres diferents: cada una ocupa el seu espai

Per tant, les projeccions 2D/3D s'han de recalcular amb cada filtratge per donar una representació fidel de l'espai actual.

**Excepció:** El dataset complet (reset) utilitza projeccions cached perquè el conjunt no canvia.

## Llindar de "poques cançons"

Quan `total_remaining ≤ 5`:
- L'API retorna `message: "Explora les N cançons per tu"`
- El frontend activa `faded=true`:
  - La visualització es torna semi-transparent
  - Apareix un overlay amb el missatge
  - Les cançons mostrades a la llista són totes les supervivents (no cal top 10)

## Garantia de mínim 1

La funció `filter_embeddings` garanteix que sempre retorna com a mínim 1 cançó. Si el filtratge eliminaria totes:
1. Es manté la cançó amb el score més alt entre les no-coincidències
2. O si no hi ha cap, es manté la primera cançó del conjunt
