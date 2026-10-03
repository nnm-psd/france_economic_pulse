# Project status and how to resume

Last updated: 2026-10-04. Read this first when you pick the project up again. The full design and every
decision (D1–D33) are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Where things stand

- **Live:** https://nnm-psd.github.io/france_economic_pulse/ (French) and `/en/` (English). It updates
  itself daily at 05:00 UTC through GitHub Actions; nothing needs to run on your computer.
- **Pages:** Estimation / Nowcast (home), Indicators, Model, Method, plus the optional
  *PIB (expérimental)* / *GDP (experimental)* page, linked from the footer and the Method page.
- **Published model:** ridge regression nowcast of monthly industrial production (IPI). Backtest: 5% better
  than a naive forecast (p = 0.07), 59% right direction, 80% range well calibrated (80.4%). Weaker than naive
  over the last 24 months. September is biased low (D21, D24).
- **GDP:** built and tested, but no model beats a naive forecast significantly (D31–D33). It's shown only on
  the experimental page.
- **Phases:** 1 (data), 2 (model), 3 (website) done. Phase 4 (automation) is waiting for **two scheduled
  05:00 UTC runs in a row** to succeed: none had run yet on 2026-10-04. Push and manual runs all deploy fine.

## Dates to watch

| Date | What happens | What to check |
|---|---|---|
| **~5 Oct 2026** | INSEE publishes August IPI | First real-time result appears on the home page and the Method page (live track record, D25) |
| From 5 Oct | Daily runs | "How the estimate has changed" chart and table fill in (D29) |
| 19 Oct 2026 | GitHub moves `ubuntu-latest` to 26.04 | Nothing: the runner is pinned to `ubuntu-24.04` |
| **~30 Oct 2026** | INSEE publishes Q3 2026 GDP (first estimate) | Compare with the experimental GDP page (models said +0.25% to +0.38%) |
| ~4 Nov 2026 | INSEE publishes September IPI | Second live result; tests whether the September bias is real |
| ~Oct 2027 | 12 months of live record | Review the model choice (recent-season variant, D24) and the GDP page |

## Open decisions (yours)

1. **Analytics:** a cookie-free service (e.g. GoatCounter) needs an account. Adding it is then a one-line change.
2. **DOI:** connect the repo to Zenodo, publish a GitHub release (e.g. `v1.0.0`), then add the DOI to
   `CITATION.cff` and the site.
3. **Model:** keep the published model (current decision) or switch to recent-season fitting. Revisit with
   the live record.
4. **3-month target:** not tested, because it changes what the site publishes.

## Backlog (not started)

- Real-time backtest on archived releases, once about a year of them exists (`data/snapshots/`).
- Daily France–Germany spread (needs a free Banque de France Webstat API key).
- GDELT news tone (rate-limited, D3).
- Comparison with INSEE and Banque de France forecasts: only meaningful for GDP, which needs a better GDP
  model first.

## How to resume on this computer (Windows)

```sh
cd d:/Code_Projects/ML/france_economic_pulse
git pull            # ALWAYS first: the bot commits data every day
uv sync
uv run pytest       # 17 offline tests
```

**Node.js** is a portable install that is **not on the system PATH**. Add it for the session first:

```sh
# Git Bash
export PATH="/c/Users/minhn/AppData/Local/Programs/node-v24.19.0-win-x64:$PATH"
# PowerShell
$env:PATH = "$env:LOCALAPPDATA\Programs\node-v24.19.0-win-x64;$env:PATH"
```

Full local refresh, in order:

```sh
uv run pipeline       # fetch new data (all 6 sources)
uv run backtest       # monthly model, ~30 s
uv run gdp-backtest   # GDP models, ~5 s
uv run experiments    # model variants, ~90 s
uv run publish        # writes site/src/data/site.json and the CSVs
cd site && npm ci && npm run build && npm run check:links
npm run preview       # http://localhost:4321/france_economic_pulse/
```

## Things that will bite you

- **Merge conflicts on `site.json`:** the bot and your local `publish` both rewrite it. Don't merge by
  hand. After `git pull --rebase` stops on it, run `uv run publish`, then `git add` both `site.json` files
  and `git rebase --continue`.
- **Lighthouse locally:** it can't launch Edge on its own on this machine. Launch Edge through Playwright
  with `--remote-debugging-port=9222`, then run `lighthouse --port=9222`. In CI, `npm run check:lighthouse`
  works as is.
- **Stopping the preview server:** stop only the `astro preview` process, not every `node.exe`.
- **Failed run emails:** a single source failing still deploys the site, and the run is marked failed so
  you're alerted. Calls retry 3 times first, so an email means a real outage. Check the "Fetch new data"
  step.
- **Rules for changes:** the master `d:/Code_Projects/CLAUDE.md` applies, including skills, YAGNI, tests for
  non-trivial logic, and audits before release. Any model change must beat the current model on the
  walk-forward backtest, with variants fixed *before* testing (D10, D24, D32).
