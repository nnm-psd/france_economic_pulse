# France Economic Pulse: Architecture

A public website that tracks the French economy using open, regularly updated data. It publishes a machine-learning **nowcast** of French industrial production: an estimate made before INSEE publishes the official figure. The data refreshes automatically in the cloud. No one downloads data by hand.

Status: phases 1–3 done; phase 4 (automation and deploy) written, waiting for GitHub Pages to be enabled and two scheduled runs to pass. Last updated: 2026-10-03.
Repository: https://github.com/nnm-psd/france_economic_pulse (public). Languages: French and English.

## 1. Overview

```
            ┌───────────────────── GitHub Actions (daily, 05:00 UTC) ─────────────────────┐
            │                                                                              │
 Open APIs ─┼─▶ 1. Ingest ─▶ 2. Store ─▶ 3. Features + model ─▶ 4. Publish JSON ─▶ 5. Build ─┼─▶ GitHub Pages
 (RTE, ECB, │    (only new     (Parquet       (nowcast +            (small files for    (Astro    │    (static site)
  INSEE,    │     rows)         in repo)       backtest)             the site)           + Plot)   │
  BODACC)   └──────────────────────────────────────────────────────────────────────────────┘
```

The rest of this document explains why each step is built the way it is. Each decision lists the alternatives considered and when to revisit it.

## 2. Product decisions

### D1. What the site says: a nowcast of French industrial production

- **Choice:** Estimate the monthly industrial production index (IPI, INSEE dataflow `IPI-2021`) for months INSEE hasn't published yet. INSEE publishes about 40 days after the month ends. Live indicators fill that gap.
- **Why:**
  - It has a clear public benchmark: each official release scores the site's estimate.
  - Monthly data gives enough history for ML.
  - Electricity consumption is known to track industrial activity.
- **Rejected:**
  - Quarterly GDP: only about 55 quarters overlap with the electricity history, too few to train on.
  - Predicting stock prices: price data can't be republished for free (see D3), and the signal is weak.
- **Revisit when:** the IPI nowcast is stable. GDP can then be added as a second target, built on the same features.

### D2. Audience and tone

- **Choice:** Analysts, students and finance professionals following France. Data-dense but readable, with a methodology page that shows the model's track record, misses included.
- **Languages: French and English, both from launch.** French is the default at `/` (the market and data are French); English is at `/en/`. See D19 for how translation works.

## 3. Data sources

Every source below was tested on 2026-10-03: it returned HTTP 200 with no API key.

| Source | Data used | Endpoint | Frequency / lag | Browser access (CORS) | Role |
|---|---|---|---|---|---|
| **RTE éCO2mix** (ODRE) | National electricity consumption | `odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/{eco2mix-national-cons-def, eco2mix-national-tr}/records`: the consolidated dataset covers 2012 to 2026-06-30; the real-time one continues from 2026-07-01 | 15 min / near real time | Yes (`*`) | Main real-time signal |
| **INSEE BDM** (SDMX) | IPI (`IPI-2021`), business climate (`CLIMAT-AFFAIRES`) | `bdm.insee.fr/series/sdmx/data/...` | Monthly | Yes | Target, plus survey features |
| **ECB Data Portal** | 10-year yields, France and Germany (`IRS/M.{FR,DE}.L.L40.CI.0000.EUR.N.Z`) | `data-api.ecb.europa.eu/service/data/...` | Monthly / about 1 month lag | Yes (`*`) | France–Germany spread as a risk feature |
| **BODACC** (DILA) | Daily count of insolvency openings: initial "Procédures collectives" notices whose judgment mentions "ouverture" (safeguard, receivership, liquidation), since 2008 | `bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/exports/csv` | Daily | Yes (`*`) | Business stress feature |
| **Open-Meteo** (CC BY 4.0) | Daily mean temperature: population-weighted mean of 8 large cities, since 2012 | `archive-api.open-meteo.com/v1/archive` | Daily / ~1 day | — | Removes the weather effect from electricity use (D4). Chosen over Météo-France station files: one request, back to 2012. |

### D3. Data that is deferred or excluded

- **GDELT news tone:** deferred to phase 5. It allows one request per 5 seconds, returned empty results during testing, and has no CORS.
- **Daily French–German spread:** deferred. Banque de France Webstat has it, but needs a free API key. The ECB monthly series is enough for a monthly target.
- **Stock prices (`yfinance`, Euronext):** excluded. Yahoo's terms forbid republishing, and Euronext data is licensed.
- **Google Trends:** excluded. There is no stable open API.
- **DVF property sales:** later. It updates twice a year, which is too slow for this target.
- **World Bank:** only for an optional page comparing France with other countries.

### D4. Electricity needs a weather correction

Heating makes French electricity demand very sensitive to temperature, so a cold month looks like an industrial boom. Before using electricity as a feature, remove the temperature effect: regress consumption on heating and cooling degree days, then use the residual. Without this step the electricity signal is misleading.

## 4. Pipeline

### D5. Language and tools: Python, managed with `uv`

- **Choice:** Python 3.12 with `requests`, `pandas`, `pyarrow` and `scikit-learn` (the weather regression is a NumPy least-squares fit, so `statsmodels` wasn't needed). `uv` manages the environment and lockfile.
- **Why:** That's the standard ML stack, and the lockfile means a CI run uses exactly the same versions as your machine. `uv` installs fast enough to matter in a daily job.
- **Rejected:** Poetry and conda, which are slower in CI with no benefit here. Orchestrators such as Airflow and Prefect: four sources and one model don't need them.

### D6. Fetch only new data

- **Choice:** Each source module reads the last date it has stored and asks the API only for data after it.
- **Why:** Runs stay fast, the job is a polite API user, and history survives even if a provider later drops old data.
- **Shape:** One file per source in `pipeline/sources/`, each exposing `parse(text)` (tested offline), `fetch(since)` and a few settings. There is no shared base class.
- **Re-fetch window (OVERLAP):** RTE 180 days (consolidated data lands ~3 months late), BODACC 14 days, temperature 10 days. INSEE and ECB are re-fetched in full every run (small, and revised).
- **INSEE series codes:** industrial production `010768261` (total industry, NAF BE, seasonally and working-day adjusted, base 2021: the target), `010768307` (manufacturing), business climate `001565530`.
- **RTE has two datasets:** the history comes from `cons-def` (loaded once) and new data from `tr`. RTE later moves months from `tr` into `cons-def` with final values, so re-read the last few months from `cons-def` every time it grows.

### D7. Storage: Parquet files committed to the repo, split per source

- **Choice:** `data/raw/<source>/<partition>.parquet`, with each source choosing its split: RTE monthly (`2026-10.parquet`), BODACC and temperature yearly, INSEE and ECB a single `all.parquet`. A file is rewritten only when its content changes.
- **Why:** No database or cloud bucket to run, and every change has a history in git. Splitting by month means a daily run rewrites only the current month's file, so the repo grows slowly. The full history is ~4.5 MB in 215 files (measured 2026-10-03). Monthly files for every source produced 1,669 files, mostly one-row INSEE months, which is why each source sets its own split.
- **RTE resolution:** kept at 30-minute steps (the consolidated dataset's resolution); the real-time dataset's 15-minute points are dropped so both datasets share keys. Consumption is a power (MW), so a daily mean is valid at either resolution.
- **Ceiling:** if the repo passes about 1 GB, move `data/` to object storage such as Cloudflare R2 (free tier) and keep only the published JSON in git.

### D8. Archive each release as published (real-time vintages)

- **Choice:** Every time INSEE publishes a new IPI figure, save a snapshot to `data/snapshots/ipi/<fetch-date>.parquet`.
- **Why:** INSEE revises past months, and its API serves only the latest figures. A backtest on revised data looks better than the model could have done in real time. From launch, the archive builds a true real-time record. Backtests on data before launch are labelled "on revised data (optimistic)".

### D9. Data checks: plain asserts, fail loudly

- **Choice:** After each fetch, check that the expected columns exist, the data isn't empty, dates are increasing and the latest point is recent enough. A failed check fails the whole run, and the site keeps serving the previous version.
- **Rejected:** Great Expectations and pandera: too heavy for four sources.

## 5. Model

### D10. Start from the simplest benchmark, add complexity only if it beats it

1. **Benchmark:** an AR(1) model on IPI growth. The nowcast has to beat it.
2. **Main model:** a bridge regression. Monthly features (weather-corrected electricity, business climate, insolvencies, yield spread) feed a ridge regression on IPI growth.
3. **Challenger:** gradient boosting (`HistGradientBoostingRegressor`). It's kept only if it beats ridge out of sample.

- **Why:** There are about 175 months of overlapping data. With so few observations, regularised linear models usually beat tree models and are easier to explain on the methodology page.

### D11. Evaluation: walk-forward, never random splits

- **Choice:** An expanding window. Train on every month up to *t*, predict *t+1*, then step forward.
- **Metrics:** RMSE and directional accuracy against the AR(1) benchmark.
- **Why:** Random k-fold splits leak future information in time series.
- **Published:** the full error history, including misses, on the methodology page.

### D12. Only features available on the nowcast date

Each feature is aligned to the date it was actually published, not the month it describes. The nowcast for month *t* runs at the start of month *t+1*:

| Data | Known up to | Features (month *t* row) |
|---|---|---|
| Industrial production (INSEE, ~40 days late) | *t−2* | `y_lag2`: latest published growth |
| Electricity, weather-corrected (D4) | *t* | `elec`, `elec_lag1`: growth of the monthly mean residual |
| Business climate (INSEE, published late in the month) | *t* | `climate` (level − 100), `climate_chg` |
| Insolvency openings (BODACC) | *t* | `insolv_yoy`: year-on-year log change (removes seasonality) |
| 10-year spread France–Germany (ECB, ~1 month late) | *t−1* | `spread_lag1`, `spread_chg_lag1` (basis points) |

The weather-correction coefficients are refitted at each backtest step using only days before the nowcast date. The same model also nowcasts month *t−1* when INSEE hasn't published it yet; that's conservative, because it ignores the extra month of known IPI.

### D20. COVID months are excluded from training, not from scoring

- **Choice:** March–July 2020 are dropped from every training set, but still counted in the "all months" score.
- **Why:** Production fell 25% and then rebounded. Trained on those months, the models learned pandemic-only patterns: business-climate change correlates 0.72 with growth with COVID included and 0.03 without. Those patterns made normal-month nowcasts worse: ridge was 24% worse than AR(1) before this change and 5% better after.
- **Not done:** dropping weak features. Their weak correlations were measured over the full sample, test period included, so selecting on them would be look-ahead bias. Ridge's regularization handles them.

### D21. Phase 2 results (2026-10-03)

Walk-forward backtest, January 2016 to July 2026 (127 months). Target: monthly growth of IPI, total industry (%). Data: latest revised vintage, so these scores are **optimistic** (D8).

| Excl. Mar–Jul 2020 | RMSE | vs AR(1) | Diebold–Mariano p (one-sided) | Right direction |
|---|---|---|---|---|
| AR(1) benchmark | 1.33 | 1.00 | — | 48% |
| **Ridge (published model)** | **1.26** | **0.95** | **0.07** | **59%** |
| Gradient boosting | 1.35 | 1.02 | 0.63 | 54% |

Over all months (COVID included), errors are dominated by 2020 and no model is meaningfully better (RMSE 3.6–3.7).

- **Published model: ridge.** Gradient boosting doesn't beat it, so per D10 it is kept only in the backtest table, for transparency.
- **Honest claim for the site:** "Slightly more accurate than a naive benchmark and right on direction about 6 times in 10; the gain is suggestive, not statistically proven." Monthly IPI growth is mostly noise (standard deviation 1.3% in normal months).
- **What carries signal:** weather-corrected electricity (correlation 0.33 with monthly growth in normal months). Business climate, insolvencies and the spread are near zero at a monthly horizon: they move slowly.
- **Known bias: September.** Weather-corrected electricity has dropped every September since 2022 (−3.0, −3.1, −2.3 and −3.4% in 2022–2026), against small changes before. The month effects are fitted on 2012–2026 as a whole, so the post-energy-crisis seasonal pattern isn't captured and September nowcasts are likely biased downward. Stated on the methodology page.
- **Candidates for improvement,** each to be tested one at a time against this baseline: month effects fitted on recent years only (fixes the September bias); French public-holiday dummies in the weather correction; electricity consumption of large industrial users only (check that RTE publishes it openly); a 3-month growth target, which is less noisy and common in central-bank nowcasts.

## 6. Website

### D13. Framework: Astro, fully static

- **Choice:** Astro (TypeScript), built to static HTML. JavaScript loads only where a chart needs it.
- **Why:**
  - A dashboard updated once a day doesn't need a server.
  - Static pages load fast and score well on Core Web Vitals.
  - Astro is mature, well documented, and supports a French version if D2 needs one.
- **Rejected:**
  - Next.js: a React runtime and server features this site doesn't use.
  - Streamlit: slow first load, little control over design, and it doesn't read as a professional site.
  - Observable Framework: a strong fit for data, but its ecosystem and future are less certain than Astro's.
- Because the site doesn't use React, `react-best-practices` doesn't apply. The design and audit skills still do.

### D14. Charts: Observable Plot

- **Choice:** Observable Plot (from the D3 team), rendered in the browser by one script (`site/src/scripts/charts.ts`) from data embedded in each chart's figure.
- **Specs (from `dataviz`):** 2px lines, 9px end dots with a 2px surface ring, hairline grid, text only in ink colours, crosshair tooltip, legend whenever there are two or more series, and a data table under every chart (tooltips are mouse-only, so the table is the keyboard and screen-reader path).
- **Palette check:** published figures blue `#2a78d6` and estimate orange `#eb6834` (dark mode `#3987e5` / `#d95926`) pass the colour-blindness and separation checks in both modes. Light-mode orange is 2.98:1 against the page, just under 3:1, so the estimate is also dashed and directly labelled.
- **Why:** It's small, made for time series, and accessible SVG output is straightforward. Chart design follows the `dataviz` skill: one palette, works in light and dark mode, no information conveyed by colour alone.
- **Rejected:** ECharts and Plotly, which are heavier, and Chart.js, whose canvas output is harder to make accessible.

### D15. The site reads files, not live APIs

- **Choice:** `uv run publish` writes one JSON file (~25 KB) to `site/src/data/site.json`, which the pages import at build time, and a copy to `site/public/data/site.json` as a public download. No browser fetch is needed, so there's no loading state and no base-path issue for data. The JSON holds no text in either language: only codes, ISO dates and raw numbers. All labels come from the site (D19), so both languages share one data file.
- **Why:**
  - Pages still load when a provider's API is down.
  - Every visitor sees the same consistent snapshot.
  - Visitor traffic never counts against API rate limits.
- **Possible addition:** a live tile showing electricity use over the last 24 hours, fetched in the browser from ODRE, which allows it.

### D19. Two languages: Astro's built-in i18n, no extra library

- **Routes:** `/` (French, default) and `/en/` (English), set with Astro's `i18n` config and `prefixDefaultLocale: false`. A switch on every page links to the same page in the other language.
- **Interface text:** two dictionaries, `site/src/i18n/fr.json` and `en.json`, with the same keys, read through one small `t(key)` helper. A test fails the build if a key is missing from either file.
- **Long text** (methodology): one Astro component per language (`MethodFr.astro`, `MethodEn.astro`), not Markdown, because the prose quotes live figures (error, p-value) that must come from the data rather than go stale.
- **French typography:** a narrow no-break space before `%` and `:`, typographic apostrophes (’), month names and number formats from `Intl`.
- **Numbers and dates:** formatted with the browser's `Intl.NumberFormat` and `Intl.DateTimeFormat` for `fr-FR` or `en-GB`. French output looks like `1 234,5` and `3 octobre 2026`. Charts use the same formatters for axes and tooltips.
- **SEO:** `<html lang>`, an `hreflang` alternate link for each version, and one sitemap covering both.
- **Rejected:** i18next and other translation libraries, which add runtime weight for three pages; automatic redirects based on browser language, which hurt SEO and annoy users who chose the other language.
- **Source names stay in the original:** INSEE, BODACC and "Procédures collectives" are proper names, and both languages show them as-is.

### D16. Pages for version 1

1. **Overview:** the latest nowcast compared with the last official figure, and a freshness date for each source.
2. **Indicators:** one chart per feature, with source and update date.
3. **Methodology and track record:** the model, its error history, the data vintages warning (D8), and attribution.

Each page exists in French and English (D19).

### D17. Quality gates before each release

- **Accessibility:** WCAG 2.2 AA, checked with the `accessibility` skill.
- **UI rules:** `web-design-guidelines` review.
- **Performance:** a `web-quality-audit` (Lighthouse) score of at least 90 in every category. Largest Contentful Paint under 2.5 s, layout shift (CLS) under 0.1.
- **Design:** visual direction set with `frontend-design` before any code: a plan for colour, type and layout tokens.
- **Both languages:** every page passes these checks in French and English. French text runs about 20% longer, so layouts must not break.
- **Result, 2026-10-03** (Lighthouse 12, mobile profile, local build): Performance 94–99, Accessibility 100, Best Practices 100, SEO 100 on all pages tested; LCP 1.7–1.8 s; CLS 0. The indicators page has the lowest performance score (TBT ~250 ms from drawing four charts on a 4× slowed CPU). Splitting the drawing into separate tasks didn't help, so it was left as is.
- **`web-design-guidelines` review:** applied typographic apostrophes, no-break spaces, tabular figures in number columns, `translate="no"` on the brand, heading scroll margins and font preloads. Deliberately not applied: Title Case headings (wrong for French; sentence case used) and language auto-detection (rejected in D19).

### D22. Visual design

- **Concept:** the page is about the time gap between now and the official figure. The hero is a sentence in the conditional tense French statistical news uses for estimates ("La production industrielle *aurait reculé*…"), followed by a fan chart: published index in blue, then the estimate dashed in orange with its 80% band. No big-number tile, no cards.
- **Type:** IBM Plex Sans Condensed 600 for headings, IBM Plex Sans for text: an engineering face for an industry subject, and the condensed width absorbs longer French headings. Fonts are self-hosted via Fontsource, not Google Fonts, so no visitor data goes to a third party (German courts have fined sites under GDPR for loading Google Fonts). The two above-the-fold faces are preloaded.
- **Colour:** "bleu de travail" (workwear blue) ink `#1d2b44` on a cool off-white `#f5f7fa`; dark mode `#eef2f7` on `#141b26`, following the OS setting. The only loud colour is the estimate's orange.
- **Layout:** left-aligned single column, text held to ~70 characters, charts full width. Vertical spacing uses flex `gap` with a non-inherited `--space` custom property, so nested sections don't pick up their parent's spacing.

## 7. Automation and hosting

### D18. GitHub Actions on a daily schedule, then GitHub Pages

- **Choice:** One workflow, `.github/workflows/update.yml`, with two jobs.
  - **Triggers:** daily at 05:00 UTC, every push to `main` (code changes go live without waiting a day) and by hand from the Actions tab. The workflow's own data commits use `GITHUB_TOKEN`, which never re-triggers a workflow, so there is no loop.
  - **`update` job:** set up Python 3.12 with `uv` (cached) → `uv sync --locked` and `pytest` → `uv run pipeline` → `uv run backtest` and `uv run publish` → commit `data/` and the site data file as `github-actions[bot]` (only if something changed; `git pull --rebase` first in case you pushed meanwhile) → Node 24 with npm cache → `npm ci` and `npm run build` → upload `site/dist` as the Pages artifact.
  - **`deploy` job:** `actions/deploy-pages` to the `github-pages` environment.
  - **Concurrency:** one run at a time and never cancelled midway, so a data commit is never cut in half.
  - **Action versions** (latest major, checked 2026-10-03): `actions/checkout@v7`, `astral-sh/setup-uv@v7`, `actions/setup-node@v7`, `actions/upload-pages-artifact@v5`, `actions/deploy-pages@v5`.
- **When a source fails:** the fetch step is allowed to fail. The pipeline still saves the sources that worked (D9), the model and site are rebuilt with the last good data for the failed source, the methodology page marks that source "late", and the site is deployed. The run then ends in failure, so GitHub emails an alert. A failure in the tests, the model or the build stops the run before deploying, and the previous site stays online.
- **One-time setup (repo owner):** Settings → Pages → Build and deployment → Source: **GitHub Actions**. The workflow can't switch this on itself: `GITHUB_TOKEN` doesn't have admin rights.
- **Why:** Free, no server to run, and the same repo holds the code, data history and site.
- **Known limits:**
  - Scheduled runs can start a few minutes late.
  - GitHub can switch off schedules on repos with no activity, but the daily data commit counts as activity.
  - Free GitHub Pages requires a public repo. That's settled: the repo is public, so the code, the data history and the model's track record are all open.
  - The site URL is `https://nnm-psd.github.io/france_economic_pulse/`, so Astro needs `base: '/france_economic_pulse'` until a custom domain is added.
- **Failure alerts:** GitHub emails you when a run fails. The methodology page marks a source "late" when its newest data point is older than that source's `MAX_AGE` (D9).
- **Rejected:** Cloudflare Pages and Netlify. Both are just as good; Pages is chosen because it keeps everything in one place. Switching later is easy.

## 8. Repository layout

```
france_economic_pulse/
├── docs/ARCHITECTURE.md        ← this file
├── pipeline/
│   ├── sources/                ← rte.py, insee.py, ecb.py, bodacc.py, weather.py
│   ├── features.py             ← monthly alignment, weather correction (D4, D12)
│   ├── model.py                ← AR(1), ridge, GBM, walk-forward backtest (D10, D11)
│   ├── publish.py              ← writes site/public/data/*.json
│   └── tests/                  ← one small test per source parser and for the backtest
├── data/
│   ├── raw/<source>/<YYYY-MM>.parquet
│   └── snapshots/ipi/<fetch-date>.parquet
├── site/                       ← Astro project: src/views (pages shared by both languages), src/pages (thin FR/EN routes),
│                                 src/i18n (fr.json, en.json, formatters), src/scripts/charts.ts, src/data/site.json
├── .github/workflows/update.yml
└── pyproject.toml / uv.lock
```

## 9. Licensing and attribution

French public data (RTE via ODRE, INSEE, BODACC/DILA) is published under the Licence Ouverte / Etalab 2.0: reuse is allowed if the source and last update date are shown. ECB data may be reused with the source cited. Open-Meteo data is CC BY 4.0 (attribution required), and its free tier is for non-commercial use; this site qualifies. Each chart shows its source and update date, and the methodology page lists every licence. **Before launch:** check each provider's licence page again.

## 10. Build plan

| Phase | Deliverable | Done when |
|---|---|---|
| 1 ✅ | Fetch modules for RTE, INSEE, ECB and BODACC, plus a temperature source | `uv run pipeline` fetches only new rows twice in a row; tests pass. Verified 2026-10-03: run 2 added 0 rows and rewrote no files; 7 tests pass. |
| 2 ✅ | Weather correction, features, AR(1) and ridge backtest | Walk-forward RMSE reported against AR(1); assumptions written up in this file. Done 2026-10-03: `uv run backtest`, results in D21; 9 tests pass. |
| 3 ✅ | Astro site, version 1 (3 pages in French and English) | Audits in D17 pass locally in both languages. Done 2026-10-03: see D17 results. |
| 4 ⏳ | Scheduled GitHub Actions run and Pages deploy | Two scheduled runs in a row succeed and the site updates. Workflow written and checked locally 2026-10-03 (valid YAML, `uv` lock current, Linux build binaries present in `package-lock.json`); waiting for Pages to be enabled. |
| 5 | Additions: GDELT tone, daily spread (Banque de France key), GDP target, custom domain | One at a time, each only if it improves the nowcast or the site |

## 11. Settled decisions

| Question | Decision (2026-10-03) |
|---|---|
| Languages | French (default, `/`) and English (`/en/`), from launch (D2, D19) |
| Repository | Public: github.com/nnm-psd/france_economic_pulse (D18) |
| Name | France Economic Pulse |

Still open: a custom domain (phase 5).
