# France Economic Pulse: Architecture

A public website that tracks the French economy using open, regularly updated data. It publishes a machine-learning **nowcast** of French industrial production: an estimate made before INSEE publishes the official figure. The data refreshes automatically in the cloud. No one downloads data by hand.

Status: phases 1–3 done and live at https://nnm-psd.github.io/france_economic_pulse/ since 2026-10-03; phase 4 deploys work (push and manual runs succeed), waiting for two scheduled runs in a row. Last updated: 2026-10-03.
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

**Further diagnostics** (normal months, computed by `model.diagnostics()` and shown on the Method page):

| | Ridge | AR(1) | Gradient boosting |
|---|---|---|---|
| MAE | 0.98 | 1.02 | 1.07 |
| Mean bias (estimate − actual) | −0.06 | −0.07 | −0.03 |
| Out-of-sample R² vs AR(1) | +9.4% | — | −3.5% |

- **The 80% range is well calibrated:** for each month, the range is built only from errors known at the time (published by *t−2*, at least 24 of them). Over 97 months since February 2018, the actual figure fell inside it **80.4%** of the time.
- **The gain hasn't held recently:** over the latest 24 months, ridge's rolling RMSE is 0.95 against AR(1)'s 0.93. The page says so.
- **The estimate is cautious:** the estimate-vs-actual scatter is flatter than the diagonal. That's expected from ridge shrinkage with a noisy target.
- **The weights are stable:** across all 127 refits, weather-corrected electricity is the only large weight and it never changes sign. The other weights stay near zero.

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
- **Palette check:** published figures blue `#2a78d6` and estimate orange `#eb6834` (dark mode `#3987e5` / `#d95926`) pass the colour-blindness and separation checks in both modes. Light-mode orange is 2.98:1 against the page, just under 3:1, so the estimate is also dashed and directly labelled. The naive forecast is aqua `#1baf7a` / `#199e70` (passes next to orange; 2.62:1 in light mode, so it has a legend and a table). Contributions use the diverging pair blue "pushes up" and red `#e34948` / `#e66767` "pushes down".
- **Colour meanings are the same on every page:** blue = published by INSEE, dashed orange = the estimate (ridge), aqua = naive forecast. Single-series diagnostic charts use orange because they describe the estimate; the weights use neutral ink.
- **Charts are drawn only when they come near the screen** (IntersectionObserver, 300 px ahead). Charts below the fold don't block the first paint. This took the methodology page, with 5 charts, from Performance 88 to 99.
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

1. **Overview:** the latest nowcast compared with the last official figure, the track record in one paragraph, **the site's four objectives** (anticipate, state the uncertainty, show everything, make public data useful) and the latest value of each signal.
2. **Indicators:** one chart per feature, with source and update date.
3. **Methodology and track record:** the model, its error history, the data vintages warning (D8), attribution, and **model diagnostics** (all metrics for all three models, interval calibration, estimate vs actual, rolling error, error distribution and weight stability; see D21).
4. **Model** (`/modele/`, `/en/model/`, added 2026-10-03): every formula with today's coefficients, the full calculation of the latest nowcast, and the code that runs. See D23.

Each page exists in French and English (D19).

### D17. Quality gates before each release

- **Accessibility:** WCAG 2.2 AA, checked with the `accessibility` skill.
- **UI rules:** `web-design-guidelines` review.
- **Performance:** a `web-quality-audit` (Lighthouse) score of at least 90 in every category. Largest Contentful Paint under 2.5 s, layout shift (CLS) under 0.1.
- **Design:** visual direction set with `frontend-design` before any code: a plan for colour, type and layout tokens.
- **Both languages:** every page passes these checks in French and English. French text runs about 20% longer, so layouts must not break.
- **Result, 2026-10-03** (Lighthouse 12, mobile profile, local build), after adding the diagnostics and lazy chart drawing: Performance 97–99, Accessibility 100, Best Practices 100, SEO 100 on every page in both languages; LCP 1.8–2.3 s; CLS 0; blocking time 0–80 ms. Before lazy drawing, the indicators page scored 94–96 and the methodology page 88–89.
- **`web-design-guidelines` review:** applied typographic apostrophes, no-break spaces, tabular figures in number columns, `translate="no"` on the brand, heading scroll margins and font preloads. Deliberately not applied: Title Case headings (wrong for French; sentence case used) and language auto-detection (rejected in D19).

### D22. Visual design

- **Concept:** the page is about the time gap between now and the official figure. The hero is a sentence in the conditional tense French statistical news uses for estimates ("La production industrielle *aurait reculé*…"), followed by a fan chart: published index in blue, then the estimate dashed in orange with its 80% band. No big-number tile, no cards.
- **Type:** IBM Plex Sans Condensed 600 for headings, IBM Plex Sans for text: an engineering face for an industry subject, and the condensed width absorbs longer French headings. Fonts are self-hosted via Fontsource, not Google Fonts, so no visitor data goes to a third party (German courts have fined sites under GDPR for loading Google Fonts). The two above-the-fold faces are preloaded.
- **Colour:** "bleu de travail" (workwear blue) ink `#1d2b44` on a cool off-white `#f5f7fa`; dark mode `#eef2f7` on `#141b26`, following the OS setting. The only loud colour is the estimate's orange.
- **Layout:** left-aligned single column, text held to ~70 characters, charts full width. Vertical spacing uses flex `gap` with a non-inherited `--space` custom property, so nested sections don't pick up their parent's spacing.

### D23. The model page: formulas, live coefficients, worked calculation, real code

- **What it shows, in 8 steps:**
  1. the target, y_t = 100·ln(IPI_t / IPI_{t−1});
  2. the weather regression, with the fitted heating and cooling coefficients;
  3. the eight inputs, with their symbols, publication lags, means and standard deviations;
  4. ridge regression: standardisation, prediction, penalised loss and the chosen α;
  5. the latest nowcast rebuilt input by input (value → z-score → × weight → contribution), with a bar chart of contributions; the previous pending month sits behind a disclosure;
  6. the 80% range;
  7. the AR benchmark with its fitted coefficients, RMSE and the Diebold–Mariano test;
  8. code excerpts.
- **Numbers come from the model that ran:** `model.explain()` refits the published ridge model and returns its intercept, α, each input's mean, scale and weight, and each pending month's values, z-scores and contributions. `publish` writes them to `site.json` under `model`. The function **asserts** that intercept + Σ contributions equals the model's own prediction, so the breakdown on the page can't drift from the published figure. The weather coefficients come from `corrected_electricity()` through `Series.attrs`.
- **Formulas:** TeX rendered at build time by KaTeX to **native MathML** (`output: "mathml"`): no client JavaScript, no math fonts, and screen readers read it. Numbers inside formulas use the page language's decimal separator. A minus is wrapped in braces so it reads as a sign, not a subtraction.
- **Code excerpts are read from the Python files at build time** (`site/src/model.ts` imports `pipeline/*.py?raw` and extracts a named top-level block), so the page always shows the code that actually ran. The build fails if a named function disappears. They are highlighted with Shiki's GitHub **high-contrast** themes: the standard GitHub light theme failed WCAG contrast (orange parameters at 3.48:1).
- **Contribution chart:** horizontal bars from zero, largest first, blue for "pushes up" and red for "pushes down" (the `dataviz` diverging pair, validated in both modes), with signed value labels and the full table below.
- **Audit (2026-10-03):** Performance 97, Accessibility 100, Best Practices 100, SEO 100 on both language versions.

### D24. Model experiments: neither variant adopted (owner's decision, 2026-10-03)

Tested against the published model on the same walk-forward backtest (127 months, normal months scored). Reproducible with `uv run experiments` (`pipeline/experiments.py`). The variants are options of `corrected_electricity` (`window_years`, `holidays`), off by default; `backtest(raw, weather=...)` passes them through.

| Variant | RMSE | vs AR(1) | DM p | Direction | RMSE, last 24 months (AR: 0.929) | September bias since 2022 |
|---|---|---|---|---|---|---|
| **Published (expanding fit)** | **1.262** | **0.952** | **0.07** | **59%** | 0.945 | −0.57 |
| Recent seasons (each year fitted on the 3 years up to it) | 1.297 | 0.978 | 0.18 | 53% | 0.917 | −0.02 |
| Public-holiday dummy | 1.267 | 0.955 | 0.07 | 56% | 0.933 | −0.56 |
| Both | 1.302 | 0.982 | 0.21 | 53% | 0.919 | 0.00 |

- **Recent seasons fix the September bias** and beat AR(1) over the last 24 months, but are worse over the full period, probably because short windows make the early years noisy.
- **Decision (owner, 2026-10-03): keep the published model.** It follows D10: a variant replaces it only if it does better over the whole test period, and 24 recent months are too few to tell progress from chance.
- **Shown on the site:** Model page, step 8 "Why this model": the table (recomputed daily by the workflow), the trade-off, the decision rule, and a line saying whether the published model still leads. The Method page's September limitation links to it.
- **When to review:** when the real-time track record (D25) covers 12 months, or sooner if a variant takes the lead over the full period (the page then says so).
- **Holidays:** no gain; dropped.
- **Not tuned further:** trying window lengths until one wins would overfit the backtest.
- **3-month growth target: not tested**, because it changes what the site publishes, not just how well. It needs an explicit decision first.

### D25. Live track record, estimate archive and release dates

- **Archive:** each `publish` run appends the day's estimates to `data/nowcasts.parquet` (made, month, estimate, 80% range), one row per day and month. The daily workflow commits it.
- **Live record** (`publish.live_record`): a month's release date and first figure come from the first IPI snapshot that contains it (D8). The estimate scored is the last one made **strictly before** that date. The site shows month, dates, estimate, INSEE's first figure, the gap and whether it fell inside the range: a summary on the home page and the full table on the Method page. Until the first release (August 2026, expected 5 October), it shows when the first result will come. Tested in `tests/test_publish.py`.
- **What changed:** under the headline, "unchanged since …" or "revised on … from …", from the archive.
- **Freshness warning:** if any source is past its `MAX_AGE`, the home page shows a status line naming it, with a link to the Method page's freshness table. Shared logic in `site/src/fresh.ts`.
- **Release dates:** INSEE has no calendar API. Its published rule is used instead: the IPI comes out 35 days after the month ends, 40 for July and November ([politique de diffusion](https://www.insee.fr/fr/metadonnees/source/indicateur/p1646/politique-diffusion)). This reproduces the July 2026 release (9 September). A weekend date moves to Monday, so the site says "around".

### D26. Sharing and discovery

- **RSS:** `/rss.xml` (French) and `/en/rss.xml`, static files built from the latest 60 archived estimates, linked in `<head>` and the footer.
- **Preview images:** `/og.png` and `/en/og.png` (1200×630), built with `sharp` from an SVG: headline plus a sparkline of the index and the estimate. Set as `og:image`, with `twitter:card` `summary_large_image`. The CI runner has no IBM Plex installed, so the image uses a system sans.
- **Dataset markup:** schema.org `Dataset` JSON-LD on the home page (description, creator, coverage, sources, JSON download, licence CC BY 4.0), for Google Dataset Search.

### D29. How the estimate evolved, and why (2026-10-03)

Modelled on the New York Fed Staff Nowcast's signature feature: show how each new data release moved the estimate.

- **What's archived daily:** in `data/nowcasts.parquet`, each pending month's exact estimate (`pred`) and input values (`x_<input>`); in `data/model_params.parquet`, the day's ridge intercept and each input's mean, scale and weight.
- **Exact decomposition** (`publish.evolution`): for the same month between two consecutive updates,
  change = Σ news_j + re-estimation, where news_j = w_j(yesterday) × (x_j(today) − x_j(yesterday)) / σ_j(yesterday).
  News values the new data with yesterday's model; re-estimation is the remainder (the model refitted on new data). News is summed by source: published production, electricity, business climate, insolvencies, rates. Tested in `tests/test_publish.py`.
- **On the home page** ("How the estimate has changed"): a step chart of the latest month's estimate at each update with its 80% band, plus INSEE's first figure once published. Below it, a table of every change split by source. Until there are two days of history, the section says when it will fill. Both states were checked, the populated one with simulated history.
- **Not reconstructed backwards:** the history starts on 2026-10-03, the first archived day. Rebuilding earlier days would need the data as it stood then, which wasn't kept.
- **Comparison with official forecasts: not done.** INSEE (*Note de conjoncture*) and the Banque de France forecast GDP, not monthly industrial production, so a fair comparison needs a GDP target first (phase 5).

### D30. Downloads and citation

- **CSV:** `publish` writes one file per series to `site/public/data/csv/` (`ipi`, `electricity`, `climate`, `insolvencies`, `spread`, `backtest`, `nowcasts`). Each chart links its file ("Download as CSV"), under CC BY 4.0 (D28).
- **Citation:** `CITATION.cff` (validated with `cffconvert`) gives the repository GitHub's "Cite this repository" button. A DOI needs the owner to connect the repository to Zenodo and publish a GitHub release.

### D28. Licences and hosting address (owner's decisions, 2026-10-03)

- **Code: MIT** ([LICENSE](../LICENSE)).
- **Data produced by the project: CC BY 4.0** ([LICENSE-DATA.md](../LICENSE-DATA.md)): archived estimates, model outputs and the site's data file. Chosen over Etalab 2.0 because it's recognised internationally, Open-Meteo already uses it, and Etalab 2.0 is designed to be compatible with CC BY.
- **Source data** in `data/raw/` and `data/snapshots/` keeps each provider's licence (Etalab 2.0 for RTE/ODRE, INSEE and DILA; the ECB reuse policy; CC BY 4.0 for Open-Meteo), listed in LICENSE-DATA.md.
- **On the site:** licences in the footer of every page and in the Method page's sources section; `license` in the Dataset markup (D26); `license` in `pyproject.toml` and `package.json`.
- **Address:** the free `https://nnm-psd.github.io/france_economic_pulse/` is kept permanently. No custom domain, so `base` stays in `astro.config.mjs`.

### D27. Automatic quality checks

- **Workflow `quality.yml`:** runs on pushes that touch `site/` and on pull requests. It's kept separate from the daily update, so a noisy score never blocks the data deploy.
- **Link check** (`npm run check:links`): every internal `href`/`src` in the built site must point to an existing file, and every `#anchor` to an existing id. Verified by planting a broken link and a broken anchor: both caught.
- **Lighthouse budget** (`npm run check:lighthouse`): 5 key pages; accessibility, best practices and SEO at least 95. Performance has a lower floor of 80 in CI, because shared runners are noisy; the 90 target is checked locally before releases.

## 7. Automation and hosting

### D18. GitHub Actions on a daily schedule, then GitHub Pages

- **Choice:** One workflow, `.github/workflows/update.yml`, with two jobs.
  - **Triggers:** daily at 05:00 UTC, every push to `main` (code changes go live without waiting a day) and by hand from the Actions tab. The workflow's own data commits use `GITHUB_TOKEN`, which never re-triggers a workflow, so there is no loop.
  - **`update` job:** set up Python 3.12 with `uv` (cached) → `uv sync --locked` and `pytest` → `uv run pipeline` → `uv run backtest` and `uv run publish` → commit `data/` and the site data file as `github-actions[bot]` (only if something changed; `git pull --rebase` first in case you pushed meanwhile) → Node 24 with npm cache → `npm ci` and `npm run build` → upload `site/dist` as the Pages artifact.
  - **`deploy` job:** `actions/deploy-pages` to the `github-pages` environment.
  - **Concurrency:** one run at a time and never cancelled midway, so a data commit is never cut in half.
  - **Runner pinned to `ubuntu-24.04`** (GitHub moves `ubuntu-latest` to 26.04 from 2026-10-19).
  - **Action versions** (latest major, checked 2026-10-03): `actions/checkout@v7`, `astral-sh/setup-uv@v7`, `actions/setup-node@v7`, `actions/upload-pages-artifact@v5`, `actions/deploy-pages@v5`.
- **When a source fails:** the fetch step is allowed to fail. The pipeline still saves the sources that worked (D9), the model and site are rebuilt with the last good data for the failed source, the methodology page marks that source "late", and the site is deployed. The run then ends in failure, so GitHub emails an alert. A failure in the tests, the model or the build stops the run before deploying, and the previous site stays online.
- **One-time setup (repo owner):** Settings → Pages → Build and deployment → Source: **GitHub Actions**. The workflow can't switch this on itself: `GITHUB_TOKEN` doesn't have admin rights.
- **Why:** Free, no server to run, and the same repo holds the code, data history and site.
- **Known limits:**
  - Scheduled runs can start a few minutes late.
  - GitHub can switch off schedules on repos with no activity, but the daily data commit counts as activity.
  - Free GitHub Pages requires a public repo. That's settled: the repo is public, so the code, the data history and the model's track record are all open.
  - The site URL is `https://nnm-psd.github.io/france_economic_pulse/`, kept permanently (D28), so Astro keeps `base: '/france_economic_pulse'`.
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
│                                 src/i18n (fr.json, en.json, formatters), src/scripts/charts.ts, src/model.ts (formulas, code excerpts), src/data/site.json
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
| 4 ⏳ | Scheduled GitHub Actions run and Pages deploy | Two scheduled runs in a row succeed and the site updates. Pages enabled and the site live on 2026-10-03; push and manual runs deploy successfully. Waiting for the first two 05:00 UTC scheduled runs. |
| 5 | Additions: quarterly GDP target (then a comparison with INSEE and Banque de France forecasts), GDELT tone, daily spread (Banque de France key), real-time backtest on archived releases once a year of them exists | One at a time, each only if it improves the nowcast or the site |

## 11. Settled decisions

| Question | Decision (2026-10-03) |
|---|---|
| Languages | French (default, `/`) and English (`/en/`), from launch (D2, D19) |
| Repository | Public: github.com/nnm-psd/france_economic_pulse (D18) |
| Name | France Economic Pulse |
| Licence | MIT for code, CC BY 4.0 for the project's data (D28) |
| Address | Free GitHub Pages address, no custom domain (D28) |
| Model | Keep the published model; trade-off explained on the Model page (D24) |

Still open: analytics (a cookie-free service such as GoatCounter needs an account) and a 3-month target (changes what the site publishes).
