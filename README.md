# TNWatch

**An independent, machine-driven civic-accountability platform for Tamil Nadu.**

TNWatch collects public-record government data, normalises it with AI agents, and
presents it as clean, sourced, accessible dashboards — so any citizen can see how
their government and their MLA are actually performing, with the receipts.

> 📖 **Start here:** read [`CONTEXT.md`](./CONTEXT.md). It is the brain of the
> project and the single source of truth. Every contributor (human or AI) reads
> it first.

## Status
Pre-build. Slice #1 = **MLA Profiles & Performance** (all 234 MLAs).

## The four verticals (built one at a time)
1. **MLA Profiles & Performance** ← building now
2. Power Cuts
3. Schemes Tracker
4. Controversy / Scam Tracker

## Stack (short version)
- **Agents (Mac Mini, 24×7):** Playwright, pdfplumber, feedparser, APScheduler
- **AI:** Ollama (local) + Gemini API
- **DB:** Supabase (PostgreSQL) · SQLite staging · Redis cache
- **Backend:** FastAPI (async) + Pydantic
- **Frontend:** Next.js + Tailwind + PWA (Vercel)
- **Delivery:** Telegram → WhatsApp (WATI) → Razorpay

See `CONTEXT.md` §4 for the full, locked stack.

## Repo layout
```
tnwatch/
├── CONTEXT.md          # master doc — READ FIRST
├── .cursor/rules       # Cursor auto-loaded conventions
├── docs/               # architecture, data sources, build plan, workflow
├── agents/             # scraper + normaliser agents (run on Mac Mini)
├── backend/            # FastAPI app + schema.sql
├── frontend/           # Next.js + PWA
├── data/               # seeds (234 constituencies), local SQLite
└── scripts/            # one-off probes and utilities
```

## Quick start (filled in as we build)
1. Read `CONTEXT.md`.
2. Copy `.env.example` → `.env`, fill in keys.
3. Create Supabase project, apply `backend/schema.sql`.
4. Seed constituencies, run the MLA scraper agent.
5. Start FastAPI, start the Next.js dev server.

## Principles
Facts, not opinions. Cite everything. Public records only. Non-partisan by design.
See `CONTEXT.md` §11.
