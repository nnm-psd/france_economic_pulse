# France Economic Pulse

Open-data nowcast of French industrial production, published as a bilingual (FR/EN) website that updates itself daily.

Design and decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run the data pipeline

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pipeline     # fetch only new data from each source into data/
uv run backtest     # walk-forward backtest + nowcast of unpublished months
uv run pytest       # offline tests
```

Data sources: RTE éCO2mix (ODRE), INSEE, ECB, BODACC (DILA), Open-Meteo. See the architecture document for licences.
