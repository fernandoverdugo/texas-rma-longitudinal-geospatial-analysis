from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_panel():
    return pd.read_csv(DATA / "rma_zip_year.csv", dtype={"zip_code": str})


def load_country():
    return pd.read_csv(DATA / "rma_zip_country_year.csv", dtype={"zip_code": str})


def load_geometry_zip_codes():
    files = sorted((DATA / "geometry").glob("rma_zip_geometries_part_*.geojson"))
    assert files
    zip_codes = []
    for path in files:
        geo = json.loads(path.read_text(encoding="utf-8"))
        assert geo["type"] == "FeatureCollection"
        zip_codes.extend(str(f["properties"]["zip_code"]).zfill(5) for f in geo["features"])
    return zip_codes


def test_expected_schema():
    panel = load_panel()
    country = load_country()
    expected_panel = {
        "fiscal_year", "zip_code", "city", "county", "total_enrollment",
        "dominant_country", "prior_year_enrollment", "yoy_pct",
        "cumulative_enrollment", "fy2019_enrollment", "change_from_fy2019_pct",
    }
    expected_country = {"fiscal_year", "zip_code", "city", "county", "country", "enrollment"}
    assert expected_panel.issubset(panel.columns)
    assert expected_country.issubset(country.columns)


def test_complete_six_year_panel():
    df = load_panel()
    assert set(df["fiscal_year"]) == {2019, 2020, 2021, 2022, 2023, 2024}
    assert df["zip_code"].nunique() == 695
    assert len(df) == 695 * 6
    assert not df.duplicated(["fiscal_year", "zip_code"]).any()


def test_expected_active_zip_counts():
    df = load_panel()
    active = df[df["total_enrollment"] > 0].groupby("fiscal_year")["zip_code"].nunique()
    assert active.to_dict() == {2019: 196, 2020: 368, 2021: 419, 2022: 529, 2023: 605, 2024: 695}


def test_country_detail_keys_are_unique_and_positive():
    df = load_country()
    assert not df.duplicated(["fiscal_year", "zip_code", "country"]).any()
    assert (df["enrollment"] > 0).all()


def test_zip_year_totals_reconcile_to_country_detail():
    panel = load_panel()
    country = load_country()
    detail = country.groupby(["fiscal_year", "zip_code"])["enrollment"].sum()
    active = panel[panel["total_enrollment"] > 0].set_index(["fiscal_year", "zip_code"])["total_enrollment"]
    aligned = detail.reindex(active.index)
    assert aligned.notna().all()
    assert (aligned.astype(int) == active.astype(int)).all()


def test_dominant_country_matches_largest_country_count():
    panel = load_panel()
    country = load_country()
    expected = (
        country.sort_values(["fiscal_year", "zip_code", "enrollment", "country"], ascending=[True, True, False, True])
        .drop_duplicates(["fiscal_year", "zip_code"])
        .set_index(["fiscal_year", "zip_code"])["country"]
    )
    active = panel[panel["total_enrollment"] > 0].set_index(["fiscal_year", "zip_code"])["dominant_country"]
    assert (expected.reindex(active.index) == active).all()
    assert (panel.loc[panel["total_enrollment"] == 0, "dominant_country"] == "No enrollment").all()


def test_yoy_calculation_reconciles():
    df = load_panel().sort_values(["zip_code", "fiscal_year"])
    prior = df.groupby("zip_code")["total_enrollment"].shift(1)
    expected = np.where(prior > 0, (df["total_enrollment"] - prior) / prior * 100, np.nan)
    mask = prior > 0
    assert np.allclose(df.loc[mask, "yoy_pct"], np.round(expected[mask], 1))
    assert df.loc[~mask, "yoy_pct"].isna().all()


def test_cumulative_enrollment_reconciles():
    df = load_panel().sort_values(["zip_code", "fiscal_year"])
    expected = df.groupby("zip_code")["total_enrollment"].cumsum()
    assert (df["cumulative_enrollment"].astype(int) == expected.astype(int)).all()


def test_fy2019_baseline_and_change_reconcile():
    df = load_panel().sort_values(["zip_code", "fiscal_year"])
    baseline = (
        df[df["fiscal_year"] == 2019]
        .set_index("zip_code")["total_enrollment"]
    )
    expected_baseline = df["zip_code"].map(baseline).astype(int)
    assert (df["fy2019_enrollment"].astype(int) == expected_baseline).all()
    mask = expected_baseline > 0
    expected_change = (df.loc[mask, "total_enrollment"] - expected_baseline[mask]) / expected_baseline[mask] * 100
    assert np.allclose(df.loc[mask, "change_from_fy2019_pct"], np.round(expected_change, 1))
    assert df.loc[~mask, "change_from_fy2019_pct"].isna().all()


def test_geometry_matches_panel_zip_codes():
    df = load_panel()
    geo_zips = load_geometry_zip_codes()
    assert len(geo_zips) == 695
    assert len(set(geo_zips)) == 695
    assert set(geo_zips) == set(df["zip_code"])


def test_no_negative_enrollment():
    panel = load_panel()
    country = load_country()
    assert (panel["total_enrollment"] >= 0).all()
    assert (country["enrollment"] >= 0).all()


def test_location_labels_are_present():
    panel = load_panel()
    country = load_country()
    assert panel[["city", "county"]].notna().all().all()
    assert country[["city", "county", "country"]].notna().all().all()
    assert (panel["city"].str.strip() != "").all()
    assert (panel["county"].str.strip() != "").all()

def test_project_summary_matches_source_data():
    summary = json.loads((DATA / "processed" / "project_summary.json").read_text())
    panel = load_panel()
    country = load_country()

    first_year = int(panel["fiscal_year"].min())
    last_year = int(panel["fiscal_year"].max())
    first = panel[panel["fiscal_year"] == first_year]
    last = panel[panel["fiscal_year"] == last_year]

    assert summary["period"] == {
        "first_fiscal_year": first_year,
        "last_fiscal_year": last_year,
    }
    assert summary["panel"]["zip_codes"] == panel["zip_code"].nunique()
    assert summary["panel"]["years"] == panel["fiscal_year"].nunique()
    assert summary["panel"]["rows"] == len(panel)
    assert summary["statewide_change"]["first_year_enrollment"] == int(first["total_enrollment"].sum())
    assert summary["statewide_change"]["last_year_enrollment"] == int(last["total_enrollment"].sum())
    assert summary["statewide_change"]["first_year_active_zip_codes"] == int((first["total_enrollment"] > 0).sum())
    assert summary["statewide_change"]["last_year_active_zip_codes"] == int((last["total_enrollment"] > 0).sum())
    assert summary["statewide_change"]["first_year_active_counties"] == first.loc[first["total_enrollment"] > 0, "county"].nunique()
    assert summary["statewide_change"]["last_year_active_counties"] == last.loc[last["total_enrollment"] > 0, "county"].nunique()

    latest_city = (
        last.groupby("city")["total_enrollment"].sum().sort_values(ascending=False)
    )
    latest_country = (
        country[country["fiscal_year"] == last_year]
        .groupby("country")["enrollment"]
        .sum()
        .sort_values(ascending=False)
    )
    assert summary["latest_year_leaders"]["city"] == latest_city.index[0]
    assert summary["latest_year_leaders"]["city_enrollment"] == int(latest_city.iloc[0])
    assert summary["latest_year_leaders"]["country"] == latest_country.index[0]
