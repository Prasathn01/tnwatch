# Data Sources — Slice #1 (MLA Profiles & Performance)

Per-source notes, what to extract, method, and gotchas. Update as you learn each
site's structure. **Every source listed here is public record.**

> ⚠️ Politics is volatile. The 17th TN Assembly (constituted May 2026) came out
> of a hung-assembly result; government and opposition can shift via defections
> and by-elections. NEVER hardcode party totals or who holds power — scrape it.

---

## 1. Wikipedia — START HERE (base list)
- **17th TN Assembly:** `en.wikipedia.org/wiki/17th_Tamil_Nadu_Assembly`
- **Per-constituency pages:** e.g. `.../Villivakkam_Assembly_constituency`
- **Extract:** member name, constituency, number, district, party, alliance,
  elected year, vote margin, vote share, total electors, Lok Sabha seat.
- **Method:** httpx + HTML parse (tables are structured). No JS needed.
- **Why first:** most complete, cleanest, single structured place to get all 234.
- **Gotcha:** names romanised inconsistently vs other sources → normaliser must
  fuzzy-match. Cross-verify party against the official site (it changes).

## 2. assembly.tn.gov.in — official record
- **Extract:** official member profiles, photos, attendance, questions, ministers/portfolios.
- **Method:** Playwright (JS-rendered, session-based navigation likely).
- **Gotcha:** structure changes without notice; build resilient selectors and a
  probe script first. Honour robots.txt + rate-limit.

## 3. PRS Legislative Research — activity metrics
- **URL:** `prsindia.org` (Tamil Nadu assembly tracking).
- **Extract:** sessions held, questions data, bills introduced/passed. Use to
  cross-reference the official numbers.
- **Method:** httpx / Playwright.
- **Gotcha:** aggregated at session level; map to individual MLAs carefully.

## 4. MyNeta / ECI affidavits — assets & criminal cases
- **URLs:** `myneta.info` (clean aggregations), `affidavit.eci.gov.in` (source PDFs).
- **Extract:** declared assets, liabilities, pending criminal cases, education, age.
- **Method:** Playwright for MyNeta tables; pdfplumber for raw ECI affidavit PDFs.
- **Gotcha:** highest-sensitivity data → present as plain sourced facts only,
  always linked. Match candidates to current MLAs by constituency + name.

## 5. tnlasdigital.tn.gov.in — debates archive
- **Extract:** speeches/debates by member (1921–present, OCR'd, searchable).
- **Method:** Playwright; query by member + assembly + date.
- **Use:** "debates_spoken" metric + later, quote-level detail. Lower priority for v1.

## 6. News sources — mentions (feeds Slice #4 later)
- The Hindu (TN), The News Minute, The Federal, New Indian Express → RSS via feedparser.
- Dinamalar, Dinamani, Vikatan (Tamil) → Playwright scrape.
- **Extract:** headline, neutral AI summary, category, severity, source + URL.
- **Gotcha:** fuzzy MLA name matching is the hard part; never editorialise summaries.

---

## Extraction etiquette (applies to all)
- Real User-Agent string identifying the project.
- Several seconds between requests; cache responses locally.
- Honour `robots.txt`. If a source disallows scraping, find an official
  API/dataset or drop it.
- Store the exact `source_url` for every fact. No source → not stored.
