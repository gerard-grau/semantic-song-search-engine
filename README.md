# Descobridor de Cançons — Semantic Song Search Engine

Motor de cerca semàntica per cançons catalanes. L'usuari escriu consultes en llenguatge natural i l'aplicació filtra progressivament un catàleg de cançons utilitzant embeddings i projeccions t-SNE per visualitzar-les en 2D i 3D.

**Stack:** React + Vite (frontend) · FastAPI (backend) · deck.gl + Three.js (visualització) · scikit-learn t-SNE (projeccions)

## Execució ràpida

- **Windows:** veure [README_WINDOWS.md](README_WINDOWS.md)
- **Linux / Mac:** veure [README_LINUX.md](README_LINUX.md)

## Documentació tècnica

Tots els documents tècnics estan a la carpeta [Documentacio/](Documentacio/):

- [arquitectura_frontend.md](Documentacio/arquitectura_frontend.md) — Estructura React, flux de dades, sistema de temes
- [arquitectura_backend.md](Documentacio/arquitectura_backend.md) — Estructura FastAPI, mòduls, funcions mock
- [visualitzacions.md](Documentacio/visualitzacions.md) — Els 4 modes de visualització
- [api_reference.md](Documentacio/api_reference.md) — Referència completa de l'API
- [filtratge_progressiu.md](Documentacio/filtratge_progressiu.md) — Com funciona el filtratge pas a pas
