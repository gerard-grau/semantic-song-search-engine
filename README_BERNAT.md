# Semantic Song Search Engine — Bernat's Implementation Notes

This document describes everything implemented during the semantic search and interactive
visualization work on top of the existing codebase.

---

## Overview

The app is a Catalan music discovery tool. Songs have high-dimensional semantic embeddings.
The user can search in natural language, and the results are shown as an interactive 2D scatter
plot where songs can be explored by clicking neighbors.

Stack: FastAPI backend + React frontend. Embeddings: `intfloat/multilingual-e5-small`.

---

## 1. Real Semantic Embeddings

**Files:** `app/backend/core/embeddings.py`, `app/backend/data/mock_songs.json`,
`scripts/reembed_mock_songs.py`

All mock/random embedding functions were replaced with real implementations using
`intfloat/multilingual-e5-small` (384-dim, L2-normalised vectors).

### Model loading

The model is loaded lazily on the first call and cached for the lifetime of the process.
CPU inference on WSL2 is feasible with e5-small (~120 MB); e5-base was too slow.

### Song embeddings

Each song is encoded as a passage using the E5 asymmetric retrieval convention:

```
"passage: {title} by {artist}. Genre: {genre}. {lyrics_snippet}"
```

The 50 mock songs in `mock_songs.json` were re-embedded from 32-dim random vectors to
real 384-dim e5-small vectors by running:

```bash
.venv/bin/python scripts/reembed_mock_songs.py
```

### Query encoding

Search queries are encoded with the `"query: "` prefix (required by E5):

```python
text_to_embedding("cançons tristes sobre l'amor")  # → 384-dim vector
```

### Semantic filter (`filter_embeddings`)

Progressive filtering with an adaptive threshold:

1. Encode the query with `text_to_embedding`
2. Compute cosine similarity against every surviving song (vectorised matrix multiply)
3. Threshold = median score — songs at or above the median survive (~top half)
4. Never returns an empty list (always at least 1 song)
5. Falls back to word-overlap scoring if embedding dimensions don't match (dev safety net)

Each successive query narrows the set further.

### Nearest neighbors (`get_nearest_neighbors`)

Returns the N most cosine-similar songs to a focal song. The focal itself is included
first with score 1.0, followed by N neighbors sorted by similarity descending.

### Neighborhood assembly (`build_neighborhood`)

Assembles the full set of songs to display when exploring a focal song. Assigns a `role`
to each song:

| Role | Meaning |
|------|---------|
| `"focal"` | The song being explored (always first) |
| `"neighbor"` | One of the N nearest neighbors |
| `"previous"` | The song navigated from (always included) |
| `"bridge"` | Most similar songs from the previous neighborhood (visual continuity anchors) |

---

## 2. Neighborhood Projection: Metric MDS + Procrustes + Snap

**File:** `app/backend/core/projections.py` — `compute_neighborhood_2d`

Replaces the previous warm-init t-SNE. Called every time the user navigates to a new
focal song.

### Algorithm (5 steps)

**Step 1 — Cosine distance matrix**

```python
normed = embeddings / ||embeddings||  # L2-normalise each row
dist_mat = 1.0 - clip(normed @ normed.T, -1, 1)  # (n × n), values in [0, 2]
```

**Step 2 — Metric MDS**

```python
MDS(metric_mds=True, metric="precomputed", n_init=4, max_iter=300)
```

Metric MDS preserves actual semantic distances (unlike t-SNE which only preserves
local topology). Songs that are semantically close appear close on screen.

**Step 3 — Centre on focal**

```python
coords -= coords[focal_idx]  # focal song is always at (0, 0)
```

**Step 4 — Normalise scale**

```python
p75 = 75th-percentile distance of non-focal songs from origin
coords /= p75  # → 75th-pct distance becomes 1.0
```

Ensures neighbors always fill the canvas around the centre regardless of absolute
embedding distances.

**Step 5 — Procrustes rotation + snap**

This is the key step for visual continuity across navigation steps.

*Phase a — Procrustes rotation:*
For songs present in both the old and new neighborhoods, find the 2D rotation R (via SVD,
det = +1) that best maps new MDS positions onto old positions:

```
M = A^T B        (A = new positions, B = old positions re-centred on new focal)
U Σ V^T = SVD(M)
R = U V^T        (flip last col of U if det < 0)
coords = coords @ R
```

This rotation is applied to ALL songs, so brand-new songs land in the correct orientation
relative to the known landmarks.

*Phase b — Snap:*
After rotation, every overlap song (present in both layouts) is placed at its exact
re-centred old position:

```python
coords[i] = (old_x - focal_old_x, old_y - focal_old_y)
```

Result: overlap songs have **zero displacement** across navigation steps. New songs get
their MDS-computed positions in the correctly-oriented frame.

### Why not t-SNE?

| | t-SNE | Metric MDS |
|--|-------|------------|
| Preserves | Local topology | Actual distances |
| Deterministic | No (random init) | Yes (with fixed seed) |
| Focal at centre | No | Yes (we enforce it) |
| Visual continuity | Warm init (approximate) | Procrustes + snap (exact) |

---

## 3. Neighborhood Exploration API

**Files:** `app/backend/api/schemas.py`, `app/backend/api/routes/search.py`

### Schemas

`Point2D` gained a `role: str` field (`"focal"` / `"neighbor"` / `"previous"` / `"bridge"`).

`NeighborsRequest`:
```python
song_id: int
n: int = 20
previous_song_id: int | None        # song navigated from
bridge_song_ids: list[int] | None   # IDs in previous neighborhood
bridge_count: int = 5
previous_positions: list[PreviousPosition] | None  # old (x, y) for each song
```

`PreviousPosition(id, x, y)` carries the 2D coordinates of songs from the previous
step back to the backend so the projection can be aligned.

### `/api/neighbors` endpoint

1. Calls `build_neighborhood` to assemble focal + neighbors + previous + bridges
2. Builds a `{id: (x, y)}` lookup from `previous_positions`
3. Calls `compute_neighborhood_2d` with the previous positions for Procrustes alignment
4. Returns songs with roles + 2D projections

---

## 4. Frontend: Exploration State (`app/frontend/src/App.jsx`)

### State

```javascript
isExploring       // bool — whether in neighborhood exploration mode
focalId           // int  — currently explored song
exploredSongTitle // str  — for the UI label
savedStateRef     // ref  — previous view (songs, proj2d, query) for back navigation
```

### Explore flow

`handleExplore(songId)`:
1. On first exploration: saves current songs/projections/query to `savedStateRef`
2. Sets `focalId`, `isExploring`, `exploredSongTitle`
3. Calls `fetchNeighbors` with `previousSongId`, `bridgeSongIds`, `bridgeCount=5`,
   and `previousPositions` (the current 2D projection)
4. Updates songs and projections with the response

`handleBack()`: restores `savedStateRef` and exits exploration mode.

### UI

When `isExploring`, a bar appears above the visualization:
```
← Enrere    Veïns de: [Song Title]    Clica una cançó per explorar-ne els veïns
```

---

## 5. Frontend: 2D Scatter Visualization (`Scatter2D.jsx`)

### Bug fixed: hover was resetting zoom/pan

The `draw` useCallback depended on `highlightedId`. Every hover triggered a new `draw`
function, which triggered `useEffect([draw])`, which called `draw()` — and inside `draw`
the view was re-initialised because `initedRef.current` was checked there.

Fix: split into two separate effects:
```javascript
// Only resets view flag — fires only when points change
useEffect(() => { initedRef.current = false }, [points])

// Only redraws — fires on any visual change
useEffect(() => { draw() }, [draw])
```

### Role-aware layered rendering

Draw order (back to front):

| Layer | Role | Style |
|-------|------|-------|
| 1 | `bridge` | Tiny dot, α=0.32 |
| 2 | `neighbor` | Normal dot |
| 3 | `previous` | Dashed-ring dot + subtle label |
| 4 | `focal` | Diamond + outer ring + bold label |
| 5 | Hovered | Enlarged circle + label |
| 6 | Pending focal | Diamond (during click animation) |

### Animated click transition

When a song is clicked, the transition happens in two phases before the neighborhood
changes:

1. **Immediate** — the clicked song switches to a diamond shape (`pendingFocalIdRef`)
2. **1050ms ease-in-out pan** — view smoothly centres on the clicked song
3. **After animation** — `onPointClick` fires, neighborhood fetch begins

The easing curve is cubic ease-in-out:
```javascript
t < 0.5 ? 4*t*t*t : 1 - (-2*t+2)^3 / 2
```

This distributes motion evenly — the midpoint is exactly 50% done, so the full 1050ms
registers as a real journey (cubic ease-out would feel done at ~500ms).

`animateTo(x, y, duration, onComplete)` uses `requestAnimationFrame` with a completion
callback. `pendingFocalIdRef` is cleared both in the callback and in `useEffect([points])`
as a race-condition guard.

### Pan & zoom

- **Scroll** — zoom anchored to cursor position, clamped to [0.2, 15×]
- **Drag** — free pan
- **Click** (< 4px movement) — triggers the animated transition

---

## 6. API Client (`app/frontend/src/api/client.js`)

```javascript
fetchNeighbors(songId, {
  previousSongId,      // for role assignment + Procrustes alignment
  bridgeSongIds,       // IDs currently on screen (bridge candidates)
  bridgeCount,         // how many bridges to inject (default 5)
  previousPositions,   // [{id, x, y}, ...] — current 2D layout
})
```

---

## Running

```bash
# Backend
.venv/bin/uvicorn app.backend.main:app --reload

# Frontend
cd app/frontend && npm run dev

# Re-embed songs (only needed once, or after changing the model)
.venv/bin/python scripts/reembed_mock_songs.py
```
