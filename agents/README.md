# agents/

Scraper and normaliser agents that run on the Mac Mini.

Each agent follows the same shape (CONTEXT.md §9):
fetch() -> parse() -> store() -> report() (writes to agent_runs).

Slice #1 agents to build (see docs/BUILD_PLAN.md):
- mla_scraper.py    Wikipedia base list -> SQLite staging
- normaliser.py     clean + fuzzy-match names (Ollama)
- eci_parser.py     assets + criminal cases (MyNeta/ECI)
- prs_activity.py   attendance, questions, bills (PRS)
- orchestrator.py   APScheduler schedule for all agents

Install deps: pip install -r requirements.txt && playwright install
