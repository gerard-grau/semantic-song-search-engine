# `app/backend/api/schemas.py`

Models Pydantic que validen entrades i sortides JSON de les rutes. No conté lògica.

## Models

| Model | Camps clau | Comentari |
| --- | --- | --- |
| `SongResult` | `id, title, artist, album, genre, year, lyrics_snippet, score` | Forma compacta retornada per llistes. |
| `SongDetail` | `+ full_lyrics, url, duration, language` | Per al popup de detall. |
| `Point2D` | `id, x, y, title, artist, genre, role` | Un punt del scatter. `role` ∈ `{"focal","neighbor","previous","bridge"}`. |
| `AllSongsResponse` | `songs, projections_2d, total` | Resposta de `GET /api/songs`. |
| `FilterRequest` | `query, similar_to_id?, song_ids?` | Body de `POST /api/filter`. `similar_to_id` activa el mode "songs similar to X" i ignora `query`. |
| `FilterResponse` | `songs, projections_2d, total_remaining, message?` | El frontend reutilitza les projeccions globals de `/api/songs`, així que `projections_2d` ve buit. |
| `PreviousPosition` | `id, x, y` | Coordenades 2D anteriors d'una cançó. |
| `NeighborsRequest` | `song_id, n, song_ids?, previous_song_id?, bridge_song_ids?, bridge_count, previous_positions?` | Per al graf de "veïns". |
| `NeighborsResponse` | `songs, projections_2d, focal_id, previous_focal_id?, total` | |
