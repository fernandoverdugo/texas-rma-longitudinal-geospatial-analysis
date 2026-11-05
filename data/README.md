# Data Dictionary

This repository uses a **synthetic longitudinal portfolio dataset** modeled on Refugee Medical Assistance program-administration patterns. All program counts are intentionally perturbed and are not intended to reproduce operational totals or client-level records. No personally identifiable information is included.

## Synthetic-data treatment

The portfolio data are perturbed at the **ZIP × country × fiscal-year** level using a deterministic random process. The treatment preserves the analytical structure needed for longitudinal analysis while changing the underlying counts:

- fiscal-year coverage remains FY2019–FY2024;
- the same 695 ZIP geographies are retained;
- the observed zero/nonzero enrollment footprint by ZIP-year is preserved, so geographic expansion can still be studied;
- nonzero country counts are perturbed rather than copied exactly;
- ZIP totals, dominant-country labels, year-over-year change, FY2019 comparisons, cumulative enrollment, rankings, and concentration measures are recomputed from the perturbed country-level data.

The dataset should therefore be interpreted as a **portfolio demonstration of analytical methods**, not as an operational report.

## `rma_zip_year.csv`

One row per fiscal year and ZIP code. This is a complete six-year panel: every ZIP represented in the project appears once for each year from FY2019 through FY2024, including zero-enrollment years.

| Field | Type | Description |
| --- | --- | --- |
| `fiscal_year` | integer | Federal fiscal year, 2019–2024. |
| `zip_code` | string | Five-digit Texas ZIP Code Tabulation Area identifier. |
| `city` | string | City label associated with the ZIP code. |
| `county` | string | County label associated with the ZIP code. |
| `total_enrollment` | integer | Synthetic RMA enrollment count for the ZIP and fiscal year. |
| `dominant_country` | string | Country of origin with the largest enrollment count in that ZIP-year; `No enrollment` when total enrollment is zero. |
| `prior_year_enrollment` | number | Prior fiscal year's enrollment for the same ZIP; blank for FY2019. |
| `yoy_pct` | number | Year-over-year percentage change when the prior-year denominator is greater than zero. |
| `cumulative_enrollment` | integer | Sum of annual synthetic enrollment for the ZIP from FY2019 through the selected year. |
| `fy2019_enrollment` | integer | FY2019 baseline enrollment for the ZIP. |
| `change_from_fy2019_pct` | number | Percentage difference between the selected year's enrollment and FY2019 when the FY2019 baseline is greater than zero. |

## `rma_zip_country_year.csv`

Long-format country-of-origin table. Only nonzero country counts are stored.

| Field | Type | Description |
| --- | --- | --- |
| `fiscal_year` | integer | Federal fiscal year, 2019–2024. |
| `zip_code` | string | Five-digit ZIP code. |
| `city` | string | City label. |
| `county` | string | County label. |
| `country` | string | Country of origin. |
| `enrollment` | integer | Synthetic enrollment count for the ZIP, country, and fiscal year. |

## `geometry/rma_zip_geometries_part_*.geojson`

Geometry-only ZIP-code boundaries used by the interactive map. The 695 features are split into several files for repository and deployment efficiency. The boundaries are simplified for web performance while preserving the ZIP topology used by the project.

## Generated analytical outputs

Running `python scripts/run_pipeline.py` creates the following derived files under `data/processed/`:

| File | Purpose |
| --- | --- |
| `statewide_year_summary.csv` | Statewide enrollment, active ZIPs/counties, and annual change. |
| `top_cities_by_year.csv` | Top city enrollment rankings for each fiscal year. |
| `top_countries_by_year.csv` | Top country-of-origin rankings for each fiscal year. |
| `country_concentration.csv` | HHI, leading-country share, top-five share, and number of represented countries. |
| `zip_persistence.csv` | First/last active year, years active, and cumulative enrollment by ZIP. |
| `project_summary.json` | Compact machine-readable summary of panel size, statewide change, geographic expansion, and latest-year leaders. |

## Interpretation notes

- **YoY** means year-over-year percentage change from the immediately preceding fiscal year.
- `change_from_fy2019_pct` is a baseline comparison, not a compounded growth rate.
- A blank percentage does not imply zero change; the percentage is undefined when the comparison denominator is zero or unavailable.
- Percentage changes can be very large when the prior-year denominator is small.
- Country composition and geographic patterns are descriptive. The project does not make causal claims about migration, policy, eligibility, or program participation.
- ZIP-code geography is an aggregate analytical unit and should not be interpreted as individual residential history.