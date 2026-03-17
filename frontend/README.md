# Frontend

This folder contains the stakeholder-facing MVP frontend built with Next.js.

## What is implemented

- landing page for the stakeholder demo
- hybrid search comparison page
- song detail page
- recommendation cards
- automatic fallback to local mock data if the backend is unavailable

## Local setup

- `npm install`
- copy [frontend/.env.local.example](.env.local.example) to `frontend/.env.local`
- `npm run dev`

## Default local URL

- `http://127.0.0.1:3000`

## Environment variable

- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`

## Main files

- [app/layout.tsx](app/layout.tsx)
- [app/page.tsx](app/page.tsx)
- [app/search/page.tsx](app/search/page.tsx)
- [app/song/[id]/page.tsx](app/song/[id]/page.tsx)
- [app/globals.css](app/globals.css)
- [lib/api.ts](lib/api.ts)
- [lib/mock-data.ts](lib/mock-data.ts)

The app is designed to consume the mock FastAPI backend when available and fall back to built-in mock data when the backend is not running.
