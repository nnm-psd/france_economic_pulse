import numpy as np
import pandas as pd

from pipeline import gdp_model


def test_quarterly_uses_complete_quarters_and_log_growth():
    months = pd.period_range("2025-01", "2025-08", freq="M")  # Q3 has only 2 months
    ipi = pd.Series(100.0, index=months)
    ipi["2025-04":"2025-06"] = 102.0
    raw = {
        "gdp": pd.DataFrame({"date": pd.to_datetime(["2025-01-01", "2025-04-01"]), "series": "gdp", "value": [100.0, 101.0]}),
        "insee": pd.DataFrame({"date": months.to_timestamp(), "series": "business_climate", "value": 100.0}),
    }
    q = gdp_model.quarterly(raw, ipi)
    assert np.isclose(q.at[pd.Period("2025Q2", "Q"), "ipi_q"], 100 * np.log(102 / 100))
    assert np.isclose(q.at[pd.Period("2025Q2", "Q"), "y"], 100 * np.log(101 / 100))
    assert pd.Period("2025Q3", "Q") not in q.index  # incomplete quarter (2 of 3 months): left out entirely


def test_expected_release_is_last_business_day_of_next_month():
    assert gdp_model.expected_release(pd.Period("2026Q3", "Q")) == "2026-10-30"  # 31 Oct is a Saturday
    assert gdp_model.expected_release(pd.Period("2025Q4", "Q")) == "2026-01-30"
