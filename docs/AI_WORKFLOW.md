# AI Coding Workflow — How to build TNWatch with Cursor + multiple LLMs

You are the architect/director. The AI is a fast junior dev. You own the
architecture, the product decisions, and the understanding. This guide is the
practical playbook.

---

## The tool split (use each for its strength)
- **Claude (chat / planning)** — architecture, schema design, debugging hard
  problems, writing/updating CONTEXT.md. Think here first.
- **Cursor (free tier)** — your main editor. Agent mode implements features
  across files. Switch models per task; plug in your own API keys to dodge limits.
  - Complex logic / careful reasoning → a Claude model.
  - Reading large files / cheap bulk edits → a Gemini model.
- **Cursor Tab / Copilot** — inline autocomplete while you type.
- **GitHub** — version control + backup. Non-negotiable.

## The per-feature loop (same as CONTEXT.md §10)
1. **Architect** in chat: "Read CONTEXT.md. Design the X agent. Contract first, no code."
2. **Review** the design yourself. Fix mismatches with the schema/pipeline.
3. **Implement** in Cursor: "Implement this per CONTEXT.md §9. Add a pytest test."
4. **Verify**: read it, run it, run the test, check the data landed.
5. **Fix**: paste errors back; iterate.
6. **Commit**: small, conventional message, push.
7. **Update CONTEXT.md** (schema + current state) in the same commit.

## Prompts that work (templates)
- **Design:** "Read CONTEXT.md. I need the `<agent/route>`. Give me the Pydantic
  models and the function signatures first — design only, no implementation yet."
- **Implement:** "Implement the design above following CONTEXT.md §9 conventions.
  Include a pytest test and update agents/requirements.txt if needed."
- **Probe (unknown site):** "Write a tiny standalone script that fetches <URL>,
  prints the structure of the relevant table/section, and saves the HTML to
  scripts/. Don't build the full agent yet."
- **Debug:** "Here's the error and the file. Diagnose root cause, propose the
  minimal fix, then apply it."
- **Review:** "Review this file against CONTEXT.md §9. List any rule violations
  and fix them."

## Habits that separate the GOAT from the amateur
- One small feature per session — never "build the whole app."
- Read and understand every file before committing it.
- Keep CONTEXT.md current — it's what makes every model produce compatible code.
- Commit small and often; push daily.
- When a site's structure is unknown, PROBE before building.
- Don't let the AI design the architecture — you do; it implements.

## Git discipline
```
main                 # always working, deployable
└── dev              # daily integration
    └── feature/...  # one feature each
```
- Branch per feature. Conventional commits. Push daily (GitHub = backup).
- Clear history means a broken scraper in month 8 is a 5-minute rollback.

## Multi-LLM consistency
The reason different models don't produce a chaotic codebase is CONTEXT.md +
.cursor/rules. They are the shared contract. If output drifts, the fix is almost
always: the model didn't read CONTEXT.md — point it back there.
