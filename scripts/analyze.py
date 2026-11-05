from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "processed"
ASSETS = ROOT / "assets"


def hhi(series):
    total = series.sum()
    if total == 0:
        return np.nan
    shares = series / total
    return float((shares ** 2).sum())


def main():
    zip_year = pd.read_csv(DATA / "rma_zip_year.csv", dtype={"zip_code": str})
    country = pd.read_csv(DATA / "rma_zip_country_year.csv", dtype={"zip_code": str})

    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    statewide = (
        zip_year.groupby("fiscal_year", as_index=False)
        .agg(
            total_enrollment=("total_enrollment", "sum"),
            active_zip_codes=("total_enrollment", lambda s: int((s > 0).sum())),
            active_counties=("county", lambda s: 0),
        )
    )

    active_counties = (
        zip_year[zip_year["total_enrollment"] > 0]
        .groupby("fiscal_year")["county"]
        .nunique()
    )
    statewide["active_counties"] = statewide["fiscal_year"].map(active_counties).fillna(0).astype(int)
    statewide["yoy_pct"] = statewide["total_enrollment"].pct_change() * 100
    statewide.to_csv(OUT / "statewide_year_summary.csv", index=False)

    city_year = (
        zip_year.groupby(["fiscal_year", "city"], as_index=False)["total_enrollment"]
        .sum()
    )
    top_cities = (
        city_year.sort_values(["fiscal_year", "total_enrollment"], ascending=[True, False])
        .groupby("fiscal_year")
        .head(10)
        .copy()
    )
    top_cities["rank"] = top_cities.groupby("fiscal_year").cumcount() + 1
    top_cities.to_csv(OUT / "top_cities_by_year.csv", index=False)

    country_year = (
        country.groupby(["fiscal_year", "country"], as_index=False)["enrollment"]
        .sum()
    )
    top_countries = (
        country_year.sort_values(["fiscal_year", "enrollment"], ascending=[True, False])
        .groupby("fiscal_year")
        .head(10)
        .copy()
    )
    top_countries["rank"] = top_countries.groupby("fiscal_year").cumcount() + 1
    top_countries.to_csv(OUT / "top_countries_by_year.csv", index=False)

    concentration_rows = []
    for year, group in country_year.groupby("fiscal_year"):
        total = group["enrollment"].sum()
        ordered = group.sort_values("enrollment", ascending=False)
        concentration_rows.append(
            {
                "fiscal_year": year,
                "country_hhi": hhi(group["enrollment"]),
                "top_country_share": ordered.iloc[0]["enrollment"] / total if total else np.nan,
                "top5_country_share": ordered.head(5)["enrollment"].sum() / total if total else np.nan,
                "countries_with_enrollment": int((group["enrollment"] > 0).sum()),
            }
        )
    concentration = pd.DataFrame(concentration_rows)
    concentration.to_csv(OUT / "country_concentration.csv", index=False)

    active = zip_year[zip_year["total_enrollment"] > 0].copy()
    persistence = (
        active.groupby("zip_code", as_index=False)
        .agg(
            city=("city", "first"),
            county=("county", "first"),
            first_active_year=("fiscal_year", "min"),
            last_active_year=("fiscal_year", "max"),
            years_active=("fiscal_year", "nunique"),
            cumulative_enrollment=("total_enrollment", "sum"),
        )
        .sort_values(["cumulative_enrollment", "zip_code"], ascending=[False, True])
    )
    persistence.to_csv(OUT / "zip_persistence.csv", index=False)

    first_year = int(statewide["fiscal_year"].min())
    last_year = int(statewide["fiscal_year"].max())
    first_row = statewide.loc[statewide["fiscal_year"] == first_year].iloc[0]
    last_row = statewide.loc[statewide["fiscal_year"] == last_year].iloc[0]
    last_city = (
        city_year[city_year["fiscal_year"] == last_year]
        .sort_values("total_enrollment", ascending=False)
        .iloc[0]
    )
    last_country = (
        country_year[country_year["fiscal_year"] == last_year]
        .sort_values("enrollment", ascending=False)
        .iloc[0]
    )
    summary = {
        "period": {"first_fiscal_year": first_year, "last_fiscal_year": last_year},
        "panel": {
            "zip_codes": int(zip_year["zip_code"].nunique()),
            "years": int(zip_year["fiscal_year"].nunique()),
            "rows": int(len(zip_year)),
        },
        "statewide_change": {
            "first_year_enrollment": int(first_row["total_enrollment"]),
            "last_year_enrollment": int(last_row["total_enrollment"]),
            "percent_change": round(
                (float(last_row["total_enrollment"]) / float(first_row["total_enrollment"]) - 1) * 100,
                1,
            ),
            "first_year_active_zip_codes": int(first_row["active_zip_codes"]),
            "last_year_active_zip_codes": int(last_row["active_zip_codes"]),
            "first_year_active_counties": int(first_row["active_counties"]),
            "last_year_active_counties": int(last_row["active_counties"]),
        },
        "latest_year_leaders": {
            "city": str(last_city["city"]),
            "city_enrollment": int(last_city["total_enrollment"]),
            "country": str(last_country["country"]),
            "country_enrollment": int(last_country["enrollment"]),
        },
        "interpretation": "Synthetic aggregate portfolio data; longitudinal and geographic patterns are descriptive, not causal or operational results.",
    }
    (OUT / "project_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    plt.figure(figsize=(8, 5))
    plt.plot(statewide["fiscal_year"], statewide["total_enrollment"], marker="o")
    plt.xlabel("Fiscal year")
    plt.ylabel("Synthetic enrollment")
    plt.title("Statewide RMA Enrollment Trend")
    plt.tight_layout()
    plt.savefig(ASSETS / "statewide_enrollment_trend.png", dpi=160)
    plt.savefig(ASSETS / "statewide_enrollment_trend.svg")
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.plot(statewide["fiscal_year"], statewide["active_zip_codes"], marker="o")
    plt.xlabel("Fiscal year")
    plt.ylabel("Active ZIP codes")
    plt.title("Geographic Expansion of Enrollment")
    plt.tight_layout()
    plt.savefig(ASSETS / "active_zip_codes_by_year.png", dpi=160)
    plt.close()

    final_city_totals = (
        city_year[city_year["fiscal_year"] == city_year["fiscal_year"].max()]
        .nlargest(5, "total_enrollment")["city"]
        .tolist()
    )
    city_pivot = city_year[city_year["city"].isin(final_city_totals)].pivot(
        index="fiscal_year", columns="city", values="total_enrollment"
    )
    plt.figure(figsize=(9, 5.5))
    for city_name in city_pivot.columns:
        plt.plot(city_pivot.index, city_pivot[city_name], marker="o", label=city_name)
    plt.xlabel("Fiscal year")
    plt.ylabel("Synthetic enrollment")
    plt.title("Enrollment Trajectories for Leading FY2024 Cities")
    plt.legend()
    plt.tight_layout()
    plt.savefig(ASSETS / "leading_city_trajectories.png", dpi=160)
    plt.close()

    top_overall_countries = (
        country.groupby("country")["enrollment"].sum().nlargest(6).index.tolist()
    )
    comp = (
        country_year[country_year["country"].isin(top_overall_countries)]
        .pivot(index="fiscal_year", columns="country", values="enrollment")
        .fillna(0)
    )
    comp_share = comp.div(
        country_year.groupby("fiscal_year")["enrollment"].sum(), axis=0
    )
    plt.figure(figsize=(9, 5.5))
    for country_name in comp_share.columns:
        plt.plot(comp_share.index, comp_share[country_name] * 100, marker="o", label=country_name)
    plt.xlabel("Fiscal year")
    plt.ylabel("Share of statewide enrollment (%)")
    plt.title("Country-of-Origin Composition Over Time")
    plt.legend()
    plt.tight_layout()
    plt.savefig(ASSETS / "country_composition_over_time.png", dpi=160)
    plt.close()

    print("Statewide summary")
    print(statewide.to_string(index=False))
    print()
    print(f"ZIP panel rows: {len(zip_year):,}")
    print(f"Unique ZIP codes: {zip_year['zip_code'].nunique():,}")
    print(f"Country-year detail rows: {len(country):,}")


if __name__ == "__main__":
    main()