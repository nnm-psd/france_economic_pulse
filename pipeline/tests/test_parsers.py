"""Parsers against trimmed copies of real API responses (no network)."""

import json

from pipeline.sources import bodacc, ecb, insee, rte, weather


def test_rte_keeps_half_hours_and_utc():
    text = (
        "date_heure;consommation\n"
        "2026-10-02T20:30:00+00:00;42411\n"
        "2026-10-02T20:45:00+00:00;42000\n"
        "2026-10-02T21:00:00+00:00;\n"
    )
    df = rte.parse(text, "tr")
    assert df["date"].astype(str).tolist() == ["2026-10-02 20:30:00"]
    assert df["consumption_mw"].tolist() == [42411]


def test_insee_sdmx():
    xml = (
        '<message:StructureSpecificData xmlns:message="m"><message:DataSet>'
        '<Series IDBANK="010768261"><Obs TIME_PERIOD="2026-07" OBS_VALUE="102.95"/>'
        '<Obs TIME_PERIOD="2026-06" OBS_VALUE="103.36"/></Series>'
        '<Series IDBANK="001565530"><Obs TIME_PERIOD="2026-09" OBS_VALUE="NaN"/></Series>'
        "</message:DataSet></message:StructureSpecificData>"
    )
    df = insee.parse(xml)
    assert df.astype(str).values.tolist() == [
        ["2026-06-01", "ipi_industry", "103.36"],
        ["2026-07-01", "ipi_industry", "102.95"],
    ]


def test_ecb_csv():
    text = (
        "KEY,REF_AREA,TIME_PERIOD,OBS_VALUE\n"
        "IRS.M.DE,DE,2026-08,3.185\n"
        "IRS.M.FR,FR,2026-08,4\n"
    )
    assert ecb.parse(text)["series"].tolist() == ["yield_10y_de", "yield_10y_fr"]


def test_bodacc_csv():
    text = "dateparution;n\n2026-10-02 00:00:00+00:00;601\n2026-10-01 00:00:00+00:00;146\n"
    df = bodacc.parse(text)
    assert df.astype(str).values.tolist() == [["2026-10-01", "146"], ["2026-10-02", "601"]]


def test_weather_weighted_mean_drops_incomplete_days():
    day = lambda temps: {"daily": {"time": ["2026-10-01", "2026-10-02"], "temperature_2m_mean": temps}}
    # Every city 10°C on day 1; one city missing on day 2.
    locations = [day([10.0, 12.0]) for _ in weather.CITIES]
    locations[-1] = day([10.0, None])
    df = weather.parse(json.dumps(locations))
    assert df.astype(str).values.tolist() == [["2026-10-01", "10.0"]]
