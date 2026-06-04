-- TNWatch — Database Schema (Slice #1: MLA Profiles & Performance)
-- Apply this to your Supabase project (SQL editor) before running agents.
-- Keep in sync with CONTEXT.md §6. Every fact-bearing row carries a source_url.

-- ---------------------------------------------------------------------------
-- Reference: 234 constituencies (mostly static)
-- ---------------------------------------------------------------------------
create table if not exists constituencies (
  id              text primary key,            -- e.g. "AC-014"
  number          int unique,                  -- assembly constituency number
  name            text not null,               -- "Villivakkam"
  district        text not null,               -- "Chennai"
  lok_sabha_seat  text,
  total_electors  int,
  reserved        text,                        -- 'GEN' | 'SC' | 'ST'
  status          text not null default 'filled'
                  check (status in ('filled', 'vacant')),  -- 'vacant' seat has no mlas row (member resigned, by-election pending)
  created_at      timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- Core: one row per current MLA
-- ---------------------------------------------------------------------------
create table if not exists mlas (
  id                 text primary key,         -- e.g. "MLA-014"
  constituency_id    text references constituencies(id),
  name               text not null,
  party              text not null,            -- scrape current value, never hardcode
  alliance           text,
  assembly_number    int default 17,
  elected_year       int,
  vote_margin        int,
  vote_share_pct     numeric(5,2),
  age                int,
  education          text,
  profession         text,
  declared_assets_cr numeric(12,2),
  liabilities_cr     numeric(12,2),
  criminal_cases     int default 0,
  is_minister        boolean default false,
  portfolio          text,
  photo_url          text,
  performance_score  numeric(5,1),
  source_url         text,                     -- provenance for the base profile (Rule 5); enriched facts carry their own source_url in mla_activity/mla_mentions
  last_updated       timestamptz default now()
);
create index if not exists idx_mlas_party on mlas(party);
create index if not exists idx_mlas_constituency on mlas(constituency_id);

-- ---------------------------------------------------------------------------
-- Assembly activity metrics (refreshed periodically)
-- ---------------------------------------------------------------------------
create table if not exists mla_activity (
  id                 bigserial primary key,
  mla_id             text references mlas(id),
  metric_date        date not null,
  attendance_pct     numeric(5,2),
  questions_raised   int default 0,
  bills_introduced   int default 0,
  debates_spoken     int default 0,
  source_url         text not null,            -- MANDATORY
  created_at         timestamptz default now()
);
create index if not exists idx_activity_mla on mla_activity(mla_id);

-- ---------------------------------------------------------------------------
-- News / mentions linked to an MLA
-- ---------------------------------------------------------------------------
create table if not exists mla_mentions (
  id            bigserial primary key,
  mla_id        text references mlas(id),
  headline      text not null,
  summary       text,                          -- AI-generated, neutral, factual
  category      text,                          -- positive|constituency|legal|statement|defection|financial
  severity      text,                          -- low|medium|high
  source_name   text not null,
  source_url    text not null,                 -- MANDATORY
  published_at  timestamptz,
  created_at    timestamptz default now()
);
create index if not exists idx_mentions_mla on mla_mentions(mla_id);

-- ---------------------------------------------------------------------------
-- Audit log: every agent run reports here (powers monitoring + freshness)
-- ---------------------------------------------------------------------------
create table if not exists agent_runs (
  id            bigserial primary key,
  agent_name    text not null,
  status        text not null,                 -- success|partial|failed
  rows_written  int default 0,
  error_message text,
  started_at    timestamptz,
  finished_at   timestamptz
);
create index if not exists idx_runs_agent_time on agent_runs(agent_name, finished_at desc);
