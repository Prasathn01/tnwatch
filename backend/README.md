# backend/

FastAPI (async) app + Pydantic models + scoring.

Files to build:
- app.py        routes: /mlas, /mlas/{id}, /constituencies, /health
- models.py     Pydantic v2 models (shared with agents)
- scoring.py    performance score (CONTEXT.md §7)
- db.py         Supabase client + Redis cache helpers
- schema.sql    canonical DB schema (apply to Supabase)
- tests/        pytest tests per route
