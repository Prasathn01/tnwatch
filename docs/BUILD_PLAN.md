# Build Plan — Slice #1 (MLA Profiles & Performance)

Commitment assumed: **20–35 hrs/week (serious push).** At this pace, Slice #1
reaches a soft launch in roughly **4–5 weeks.** Each item is sized so you finish
something runnable in a session.

> Rule: nothing is "done" until it runs end-to-end AND CONTEXT.md §12 is updated.

---

## Week 0 — Foundations (one sitting, ~3–4 hrs)
- [ ] `git init`, push empty repo to GitHub, protect `main`.
- [ ] Drop in `CONTEXT.md`, `.cursor/rules`, `README.md`, `.env.example`.
- [ ] Create Supabase project. Save URL + keys to `.env`.
- [ ] Python env: `python -m venv .venv`, install deps (see `agents/requirements.txt`).
- [ ] Install Ollama on the Mac Mini, pull `llama3.2`. Confirm it answers locally.
- [ ] Verify Cursor reads `.cursor/rules` (ask it "what are the project rules?").

## Week 1 — The data spine (scrape → stage → store)
- [ ] Apply `backend/schema.sql` to Supabase.
- [ ] Seed the 234 `constituencies` (scrape Wikipedia list once; store as `data/constituencies.json` then load).
- [ ] **MLA Scraper Agent** (`agents/mla_scraper.py`): Wikipedia base list →
      SQLite staging. fetch/parse/store/report. Pytest test.
- [ ] **Normaliser Agent** (`agents/normaliser.py`): clean staged rows, fuzzy
      name match against constituencies, via Ollama. Test on 10 rows.
- [ ] **Validator + push**: Pydantic-validate, upsert clean rows into Supabase `mlas`.
- [ ] Sanity check: 234 MLA rows in Supabase, each with party + constituency.

## Week 2 — Enrich the profiles
- [ ] **ECI/Affidavit Parser** (`agents/eci_parser.py`): MyNeta → assets,
      liabilities, criminal cases, education. pdfplumber where needed.
- [ ] **PRS Activity Agent** (`agents/prs_activity.py`): attendance, questions,
      bills → `mla_activity` (every row sourced).
- [ ] **Performance score** (`backend/scoring.py`): implement §7 formula. Unit-tested.
- [ ] Re-run pipeline; confirm enriched, scored rows in Supabase.

## Week 3 — The face (read path)
- [ ] **FastAPI** (`backend/app.py`): `/mlas`, `/mlas/{id}`, `/constituencies`,
      `/health`. Redis cache on list endpoints. Tests for each route.
- [ ] Deploy FastAPI to Render (free). Confirm public JSON.
- [ ] **Next.js**: MLA list page (search + filter by party/district), MLA detail
      page (profile + score breakdown + sourced links), constituency page.
- [ ] Wire frontend to the API. Deploy to Vercel. PWA manifest + installable.

## Week 4 — Make it run forever + soft launch
- [ ] **APScheduler orchestrator** (`agents/orchestrator.py`) on Mac Mini:
      MLA refresh daily, news (later) more often.
- [ ] **Monitoring**: each agent pings Healthchecks.io on success; daily freshness
      check ("newest row < 36h old?") alerts you if a scraper silently dies.
- [ ] Sentry on backend + frontend for error tracking.
- [ ] Polish the MLA detail page (this is the shareable unit). Add OG images.
- [ ] **Soft launch** to ~50 people (friends, r/Chennai, a few WhatsApp groups).
      Watch what they actually click. Take notes.

## After Slice #1
- Pick Slice #2 (Power Cuts). It reuses this exact pipeline — much faster now.
- Only then consider monetisation + mobile apps (see CONTEXT.md §13).

---

## Definition of done for Slice #1
A visitor can open the site, search any of 234 MLAs, see a sourced profile with a
transparent performance score, and the data refreshes itself daily on the Mac
Mini without you touching it — and you get alerted if anything breaks.
