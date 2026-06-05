# TNWatch — Master Context Document

> **This is the single source of truth for the project.** Every AI coding session
> (Cursor, Claude, Gemini, Claude Code) must read this file FIRST before writing
> any code. If anything you are about to build contradicts this file, stop and
> fix the contradiction here first. Keep this file updated as the project evolves.

---

## 0. How to use this document

- **Humans:** Read top to bottom once. After that, jump to the section you need.
- **AI assistants:** Read fully at the start of every session. Obey Section 9
  (Engineering Rules) and Section 10 (Build Loop) without exception.
- **Update discipline:** When you finish a feature, update Section 12 (Current
  State) and Section 6 (DB Schema) in the same commit. A stale CONTEXT.md is
  worse than none.

---

## 1. What TNWatch is

TNWatch is an independent, machine-driven civic-accountability platform for
**Tamil Nadu**. It collects public-record government data from many sources,
normalises it, and presents it as clean, sourced, accessible dashboards so any
citizen can see how their government and their elected representatives are
actually performing.

**One-line pitch:** *"See exactly how the Tamil Nadu government and your MLA are
performing — with the receipts."*

**Core principle that protects us:** We publish **facts with sources**, never
opinions or accusations. "MLA X attended 47% of sessions (source: assembly.tn.gov.in)"
is a fact and is unchallengeable. "MLA X is lazy" is an opinion and is a lawsuit.
We only ever do the former. See Section 11 (Legal & Ethical Guardrails).

---

## 2. The full vision (all four verticals)

The platform will eventually cover four data verticals. **We build them ONE AT A
TIME.** The vision is big; the build is sequential. Do not build all four at once.

| # | Vertical | What it tracks | Build order |
|---|----------|----------------|-------------|
| 1 | **MLA Profiles & Performance** | All 234 MLAs: profile, assets, criminal cases, attendance, questions, bills, news | **SLICE #1 — build now** |
| 2 | **Power Cuts** | Scheduled + reported outages by area, duration, reason, trends | Slice #2 |
| 3 | **Schemes Tracker** | Govt schemes: announced → budgeted → implemented → beneficiaries reached | Slice #3 |
| 4 | **Controversy / Scam Tracker** | Documented controversies tied to politicians, sourced to news + court records | Slice #4 (highest legal care) |

Each vertical reuses the SAME pipeline pattern proven by Slice #1:
**fetch → stage → normalise → validate → store → serve → display.**

---

## 3. Why MLA Profiles is Slice #1

- **Finite, clean scope.** Exactly 234 MLAs. A bounded list, not an infinite stream.
- **Structured public sources.** Wikipedia per-constituency pages, assembly.tn.gov.in,
  PRS, and MyNeta/ECI affidavits are all well-structured.
- **High shareability.** "Your MLA's report card" is something people screenshot and share.
- **Sets the full pattern.** It exercises every stage of the pipeline (scrape,
  PDF parse, AI normalise, score, store, display) so Slices 2–4 become copy-paste.
- **Moderate legal risk** (lower than the scam tracker), as long as we stick to
  sourced facts.

> ⚠️ **Live political data note:** The 17th Tamil Nadu Assembly was constituted in
> May 2026 after a hung-assembly result; C. Joseph Vijay (TVK) heads the government,
> Udhayanidhi Stalin (DMK) is Leader of Opposition. **Never hardcode seat counts,
> party totals, or who is in power.** Always scrape current values. Politics here
> changes fast (defections, by-elections). Treat all political facts as volatile.

---

## 4. Tech Stack (locked)

### Data layer — runs on Mac Mini, 24×7
- **Playwright** (Python) — browser scraping for JS-rendered pages
- **httpx** — simple HTTP fetches for static pages / APIs
- **pdfplumber** + **camelot-py** — extract text and tables from government PDFs
- **feedparser** — RSS monitoring for news sources
- **APScheduler** — schedules all agent jobs locally (no external cron service)

### AI / processing layer
- **Ollama** (local on Mac Mini, e.g. `llama3.2`) — high-volume cheap tasks:
  classification, fuzzy name matching, deduplication
- **Gemini API** — complex reasoning: extracting structure from messy text,
  summarising, Tamil translation
- **scikit-learn** — simple statistical work (trend detection, anomaly flags). No
  model training, no GPU needed.

> **Where the LLMs actually engage:** the *base-profile* Normaliser (Slice #1,
> Wikipedia → `mlas`) is **purely deterministic** — string cleaning + a party map
> + Pydantic validation, no Ollama/Gemini. The constituency link is already known
> (the scraped constituency number → `AC-NNN`), so there is no fuzzy matching at
> this stage. Ollama (fuzzy name matching, dedup) and Gemini (messy-text
> extraction, Tamil) come in at the **enrichment** agents (ECI/PRS/news), which
> arrive with external names that must be matched back to these MLAs.

### Database
- **Supabase (PostgreSQL)** — cloud source of truth + Auth
- **SQLite** — local staging DB on Mac Mini (dirty data lands here first)
- **Redis** — cache for hot data (today's scores, current MLA list). Local free
  tier to start.

### Backend
- **FastAPI** (async) — REST + WebSocket API, Python 3.12
- **Pydantic v2** — every data model is a Pydantic model. No loose dicts.
- **Celery** — background tasks (bulk alerts, report generation) — added later
- **Supabase Auth** — user accounts / subscription tiers

### Frontend
- **Next.js** (App Router) + **TypeScript** — web + PWA (installable on Android/iOS)
- **Tailwind CSS** — styling
- **Recharts** — charts (attendance, trends)
- **Mapbox GL** — TN district / constituency map
- **Vercel** — hosting (free tier)

### Delivery & monetisation (later slices)
- **Telegram Bot** — free alert channel, launch here first
- **WhatsApp via WATI** — paid alerts
- **Resend** — email
- **Razorpay** — subscriptions / payments

### Hosting summary
| Component | Host | Cost at start |
|-----------|------|---------------|
| Agents + Ollama + SQLite | Mac Mini (yours) | ₹0 |
| PostgreSQL + Auth | Supabase free tier | ₹0 |
| FastAPI | Render free tier | ₹0 |
| Next.js | Vercel free tier | ₹0 |
| CDN / SSL | Cloudflare free | ₹0 |
| Gemini API | pay-as-you-go | ~₹500/mo |
| Domain | registrar | ~₹800/yr |

---

## 5. System Architecture

```
┌──────────────────────────── MAC MINI (local, 24×7) ────────────────────────────┐
│                                                                                 │
│   APScheduler (orchestrator)                                                    │
│        │  triggers each agent on its schedule                                   │
│        ▼                                                                        │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│   │ MLA Scraper  │  │ ECI/Affidavit│  │ PRS Activity │  │ News Monitor │        │
│   │ Agent        │  │ Parser Agent │  │ Agent        │  │ Agent        │        │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│          └────────────────┬┴──────────────────┴─────────────────┘               │
│                           ▼                                                      │
│                  SQLite staging DB (dirty data)                                  │
│                           │                                                      │
│                           ▼                                                      │
│                  Normaliser Agent (Ollama local + Gemini API)                    │
│                  → clean, classify, fuzzy-match names, score                     │
│                           │                                                      │
│                           ▼                                                      │
│                  Validator (Pydantic schema check; reject bad rows)              │
│                           │                                                      │
│                           ▼ push clean rows                                      │
└───────────────────────────┼─────────────────────────────────────────────────────┘
                            │
                            ▼
                  ┌───────────────────────┐
                  │ Supabase (PostgreSQL) │  ← source of truth
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │ FastAPI (Render)      │  ← REST + WebSocket
                  │ + Redis cache         │
                  └───────────┬───────────┘
                              │
              ┌───────────────┼─────────────────┐
              ▼               ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ Next.js +PWA │  │ Telegram bot │  │ WhatsApp/    │
    │ (Vercel)     │  │ (free)       │  │ email alerts │
    └──────────────┘  └──────────────┘  └──────────────┘
```

**The golden rule of the pipeline:** every stage is independent and can fail
without crashing the others. A broken scraper flags itself and is skipped; it
never takes down the API or the site.

---

## 6. Database Schema (keep this updated)

> This is the current schema. Update it in the SAME commit whenever you change
> tables. The canonical SQL lives in `backend/schema.sql`.

### Slice #1 tables (MLA vertical)

```sql
-- 234 constituencies (mostly static reference data)
constituencies (
  id              text primary key,        -- e.g. "AC-014"
  number          int unique,              -- assembly constituency number
  name            text not null,           -- "Villivakkam"
  district        text not null,           -- "Chennai"
  lok_sabha_seat  text,
  total_electors  int,
  reserved        text,                    -- 'GEN' | 'SC' | 'ST'
  status          text default 'filled',   -- 'filled' | 'vacant' (vacant seat has no mlas row)
  created_at      timestamptz default now()
)

-- One row per current MLA (the heart of Slice #1)
mlas (
  id                 text primary key,      -- e.g. "MLA-014"
  constituency_id    text references constituencies(id),
  name               text not null,
  party              text not null,         -- scrape current value, never hardcode
  alliance           text,
  assembly_number    int default 17,        -- 17th assembly
  elected_year       int,
  vote_margin        int,
  vote_share_pct     numeric(5,2),
  age                int,
  education          text,
  profession         text,
  declared_assets_cr numeric(12,2),         -- crore, from ECI affidavit
  liabilities_cr     numeric(12,2),
  criminal_cases     int default 0,         -- count from ECI affidavit
  is_minister        boolean default false,
  portfolio          text,
  photo_url          text,
  performance_score  numeric(5,1),          -- calculated; see Section 7
  source_url         text,                  -- provenance for the base profile (Rule 5)
  last_updated       timestamptz default now()
)

-- Assembly activity metrics, refreshed periodically
mla_activity (
  id                 bigserial primary key,
  mla_id             text references mlas(id),
  metric_date        date not null,
  attendance_pct     numeric(5,2),
  questions_raised   int default 0,
  bills_introduced   int default 0,
  debates_spoken     int default 0,
  source_url         text not null,         -- MANDATORY: every row is sourced
  created_at         timestamptz default now()
)

-- News / mentions linked to an MLA (feeds controversy flags later)
mla_mentions (
  id            bigserial primary key,
  mla_id        text references mlas(id),
  headline      text not null,
  summary       text,                       -- AI-generated, neutral, factual
  category      text,                       -- 'positive'|'constituency'|'legal'|'statement'|'defection'|'financial'
  severity      text,                       -- 'low'|'medium'|'high'
  source_name   text not null,
  source_url    text not null,              -- MANDATORY
  published_at  timestamptz,
  created_at    timestamptz default now()
)

-- Audit log: every scrape run reports here (powers monitoring + freshness checks)
agent_runs (
  id            bigserial primary key,
  agent_name    text not null,
  status        text not null,              -- 'success'|'partial'|'failed'
  rows_written  int default 0,
  error_message text,
  started_at    timestamptz,
  finished_at   timestamptz
)
```

`mlas.source_url` records where the **base profile** came from (the Wikipedia
members list for Slice #1). It is a single `text` column, not `jsonb`: as
enrichment agents (ECI, PRS, news) add facts, those facts live in their own rows
(`mla_activity`, `mla_mentions`) which already carry their own `source_url`. So
each fact stays traceable to exactly one source without overloading `mlas`.

A currently-vacant seat (member resigned, by-election pending) has **no `mlas`
row**; instead `constituencies.status = 'vacant'`. Vacancy is derived, not
scraped: the set of constituencies with no staged MLA = the vacant seats (the
Normaliser sets their status). As of 2026-06-04 there are 5 such seats.

Tables for Slices 2–4 (power_cuts, schemes, controversies) will be added when we
reach them, following the same conventions: every fact-bearing row MUST carry a
`source_url`.

---

## 7. The MLA Performance Score (transparent methodology)

The score is **public, documented, and purely formulaic** — never subjective.
This transparency is what makes it defensible. Starting weights (tune later with
real data; whatever the weights are, they are published on the site):

| Component | Weight | Source |
|-----------|--------|--------|
| Assembly attendance % | 30% | assembly.tn.gov.in / PRS |
| Questions raised (normalised) | 20% | PRS |
| Bills / debates participation | 15% | PRS / tnlasdigital |
| Pending criminal cases (inverse) | 20% | ECI affidavit |
| Asset growth reasonableness | 5% | ECI affidavits over time |
| Constituency activity (sourced news) | 10% | News monitor |

Score is 0–100. The page always shows the breakdown and links every input to its
source. We never show a score without its receipts.

---

## 8. Data Sources (Slice #1)

| Source | URL | What we get | Method |
|--------|-----|-------------|--------|
| Wikipedia — 17th TN Assembly + per-constituency pages | en.wikipedia.org | Member list, constituency, party, vote margins, electors | httpx + parse (best starting source — very structured) |
| TN Assembly official | assembly.tn.gov.in | Official member profiles, attendance, questions | Playwright |
| PRS Legislative Research | prsindia.org | Sessions, questions, bills (cross-reference) | httpx / Playwright |
| MyNeta / ECI affidavits | myneta.info, affidavit.eci.gov.in | Assets, liabilities, criminal cases, education | Playwright + pdfplumber |
| TN Assembly debates archive | tnlasdigital.tn.gov.in | Speeches/debates (1921–present, searchable) | Playwright |
| News (later: feeds controversy) | thehindu.com, thenewsminute.com, thefederal.com, dinamalar.com | Mentions, controversies | feedparser + Playwright |

**Start with Wikipedia.** It gives a clean, complete 234-MLA base list with
constituency, party, and vote data in one structured place. Layer the official +
ECI + PRS sources on top to enrich and verify.

See `docs/DATA_SOURCES.md` for per-source notes, selectors, and gotchas.

---

## 9. Engineering Rules (non-negotiable)

1. **Every data model is a Pydantic v2 model.** No passing around loose dicts.
2. **Everything async** in the backend (`async def`, `httpx.AsyncClient`, async DB driver).
3. **`snake_case`** for Python/DB, **`camelCase`** for TypeScript/React.
4. **Every agent follows the same shape:** `fetch()` → `parse()` → `store()`,
   plus a `report()` that writes to `agent_runs`.
5. **Every fact-bearing row carries a `source_url`.** No source, no store.
6. **No secrets in code.** Use `.env` (and `.env.example` committed as a template).
7. **Scrapers must be resilient:** try multiple selectors, time out gracefully,
   never crash the orchestrator. A failed scrape logs `failed` and moves on.
8. **Idempotent writes:** use upserts keyed on stable IDs so re-running an agent
   never creates duplicates.
9. **Read before write:** an AI must read the file it is about to edit (and this
   CONTEXT.md) before changing it.
10. **One feature per branch, one concern per commit.** Conventional commits
    (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`).
11. **Tests alongside code.** Every agent and every API route ships with at least
    one test. Use `pytest`.
12. **Respect the sources:** honour `robots.txt`, rate-limit politely (a few
    seconds between requests), set a real User-Agent, cache aggressively. We are
    good citizens of the public web.

---

## 10. The Build Loop (follow this for EVERY feature)

```
1. ARCHITECT  (Claude / planning)
   "Read CONTEXT.md. Design the <X> agent/route. Give the data contract
    and structure FIRST — no full code yet."
        │
2. REVIEW     (you)
   Does the design fit the pipeline + schema? Adjust before any code.
        │
3. IMPLEMENT  (Cursor agent)
   "Implement this design following CONTEXT.md §9. Include a pytest test."
        │
4. VERIFY     (you)
   Read the code. Run it. Run the test. Check data landed in SQLite/Supabase.
        │
5. FIX        (paste any error back to the AI; iterate)
        │
6. COMMIT
   git add -p && git commit -m "feat: <thing>" && git push
        │
7. UPDATE CONTEXT.md  (§6 schema if changed, §12 current state)
        │
   → next feature
```

**Mindset:** You are the architect and director. The AI is a fast junior dev.
You own the architecture, the product calls, and the understanding. Never merge
code you cannot explain in one sentence.

---

## 11. Legal & Ethical Guardrails

- **Facts, not opinions.** Publish sourced data. Let readers form conclusions.
- **Cite everything.** Every claim links to its public source. Unsourced → not published.
- **Public records only.** ECI affidavits, assembly records, published news,
  government PDFs. No private data, no hacking, no paywalled content.
- **Neutral language.** "X has N pending cases (source)" — never "X is a criminal."
- **Right of reply / correction.** Provide a visible way to report errors; fix
  promptly and log corrections.
- **No targeting of private individuals.** Only public officials acting in office.
- **Respect copyright.** Summarise and link; never republish full articles.
- This is **journalism-grade data work**, modeled on PRS Legislative Research's
  non-partisan stance. Neutrality is both the ethic and the legal shield.

---

## 12. Current State (update every session)

- [ ] Repo + CONTEXT.md created
- [ ] `.env.example` + secrets plan
- [ ] Supabase project created, `schema.sql` applied
- [x] Constituencies seed (234 rows) — `scripts/seed_constituencies.py` → `data/constituencies.json`, loaded into Supabase via `--load`; 234 rows verified (SC 43, ST 2). [2026-06-04]
- [x] **MLA Scraper Agent** — Wikipedia base list → SQLite staging. `agents/mla_scraper.py`, fetch/parse/store/report, idempotent upsert, 9 pytest tests, live run stages 229 sitting MLAs (5 vacant seats correctly excluded). [2026-06-04]
- [x] Normaliser agent — `agents/normaliser.py` (deterministic: footnote/whitespace/honorific cleaning, `PARTY_MAP`, `AC-NNN` link). No Ollama needed for base profile (see §4). [2026-06-05]
- [x] Validator + push to Supabase — Pydantic `MLACleanRecord` validates; `agents/supabase_io.py` upserts `mlas`; 229 MLAs + 5 vacant seats flipped; verified live. [2026-06-05]
- [ ] ECI/affidavit parser (assets, criminal cases)
- [ ] PRS activity agent (attendance, questions, bills)
- [ ] Performance score calculation
- [ ] FastAPI: `/mlas`, `/mlas/{id}`, `/constituencies` routes
- [ ] APScheduler orchestrator running on Mac Mini
- [ ] Next.js: MLA list page, MLA detail page, constituency page
- [ ] Monitoring: Healthchecks.io pings + freshness check
- [ ] Soft launch (slice #1) to ~50 people

> Legend: `[ ]` not started · `[~]` in progress · `[x]` done.
> When you check a box, note the date and the commit hash next to it.

---

## 13. Roadmap beyond Slice #1

- **Slice #2 — Power cuts:** TANGEDCO + LiveChennai scrape, area schedules, alerts.
- **Slice #3 — Schemes:** budget-doc PDF parsing, announced→delivered pipeline.
- **Slice #4 — Controversy tracker:** news + court-record sourced, highest legal care.
- **Mobile apps:** wrap in Expo/React Native once web/PWA has real traction.
- **Monetisation:** free tier → Citizen Pro (₹49/mo) → Journalist API (₹999/mo)
  → Enterprise (₹4,999/mo) → grants/partnerships.
- **Tamil-language UI + alerts** for mass reach.

---

## 14. Glossary

- **Agent** — a Python class that fetches from one source and stages data.
- **Slice** — one complete vertical (e.g. MLA), built end-to-end before the next.
- **Staging** — the local SQLite dirty-data holding area before normalisation.
- **Source of truth** — Supabase PostgreSQL; the clean, canonical data.
- **MLA** — Member of the Legislative Assembly (234 in Tamil Nadu).
- **PRS** — PRS Legislative Research, a non-partisan tracker we model ourselves on.
- **ECI** — Election Commission of India (affidavits = assets/criminal disclosures).

---

*Last updated: 2026-06-04 · Keep this file alive. It is the brain of the project.*
