# France Economic Pulse

Open-data nowcast of French industrial production, published as a bilingual (FR/EN) website that updates itself daily.

Live site: https://nnm-psd.github.io/france_economic_pulse/ (English: `/en/`).
Design and decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How it updates

A GitHub Actions workflow ([update.yml](.github/workflows/update.yml)) runs daily at 05:00 UTC, on every push to `main`, and on demand from the Actions tab. It fetches new data, refits the nowcast, commits the data, rebuilds the site and deploys it to GitHub Pages. If a data source is down, the site is still rebuilt with that source's last good data and the run is marked failed so you get an email.

A second workflow ([quality.yml](.github/workflows/quality.yml)) checks internal links and a Lighthouse budget on every change to the site.

Follow new estimates by RSS: [français](https://nnm-psd.github.io/france_economic_pulse/rss.xml), [English](https://nnm-psd.github.io/france_economic_pulse/en/rss.xml).

## Run the data pipeline

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pipeline     # fetch only new data from each source into data/
uv run backtest     # walk-forward backtest + nowcast of unpublished months
uv run pytest       # offline tests
```

## Build the website

Requires Node.js 22 or later.

```sh
uv run backtest && uv run publish   # refresh the site's data file
cd site && npm install && npm run build   # static site in site/dist
npm run preview                     # http://localhost:4321/france_economic_pulse/
```

Data sources: RTE éCO2mix (ODRE), INSEE, ECB, BODACC (DILA), Open-Meteo. See the architecture document for licences.
