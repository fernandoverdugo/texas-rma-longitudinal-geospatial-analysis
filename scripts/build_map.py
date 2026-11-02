from pathlib import Path
import json
import math

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"


def clean_number(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def main():
    zip_year = pd.read_csv(DATA / "rma_zip_year.csv", dtype={"zip_code": str})
    country = pd.read_csv(DATA / "rma_zip_country_year.csv", dtype={"zip_code": str})
    geometry_files = sorted((DATA / "geometry").glob("rma_zip_geometries_part_*.geojson"))
    if not geometry_files:
        raise FileNotFoundError("No geometry files found in data/geometry.")
    geometry = {"type": "FeatureCollection", "features": []}
    for geometry_file in geometry_files:
        part = json.loads(geometry_file.read_text(encoding="utf-8"))
        geometry["features"].extend(part["features"])

    top_by_zip_year = {}
    for (year, zip_code), group in country.groupby(["fiscal_year", "zip_code"]):
        top = (
            group.sort_values(["enrollment", "country"], ascending=[False, True])[["country", "enrollment"]]
            .to_dict("records")
        )
        top_by_zip_year[(int(year), zip_code)] = top

    zip_payload = {}
    for row in zip_year.itertuples(index=False):
        zip_payload.setdefault(row.zip_code, {})[str(int(row.fiscal_year))] = {
            "city": row.city,
            "county": row.county,
            "total": int(row.total_enrollment),
            "dominant": row.dominant_country,
            "yoy": clean_number(row.yoy_pct),
            "cumulative": int(row.cumulative_enrollment),
            "fy2019": int(row.fy2019_enrollment),
            "from2019": clean_number(row.change_from_fy2019_pct),
            "topCountries": top_by_zip_year.get((int(row.fiscal_year), row.zip_code), []),
        }

    year_summary = {}
    for year, group in zip_year.groupby("fiscal_year"):
        active = group[group["total_enrollment"] > 0]
        city_totals = (
            active.groupby("city")["total_enrollment"].sum().sort_values(ascending=False)
        )
        country_totals = (
            country[country["fiscal_year"] == year]
            .groupby("country")["enrollment"]
            .sum()
            .sort_values(ascending=False)
        )
        year_summary[str(int(year))] = {
            "total": int(group["total_enrollment"].sum()),
            "activeZips": int((group["total_enrollment"] > 0).sum()),
            "counties": int(active["county"].nunique()),
            "topCity": city_totals.index[0] if len(city_totals) else "—",
            "topCityValue": int(city_totals.iloc[0]) if len(city_totals) else 0,
            "topCountry": country_totals.index[0] if len(country_totals) else "—",
            "topCountryValue": int(country_totals.iloc[0]) if len(country_totals) else 0,
            "topCities": [
                {"name": str(k), "value": int(v)} for k, v in city_totals.head(5).items()
            ],
            "topCountries": [
                {"name": str(k), "value": int(v)} for k, v in country_totals.head(5).items()
            ],
        }

    overall_top = (
        country.groupby("country")["enrollment"].sum().nlargest(10).index.tolist()
    )

    geometry_json = json.dumps(geometry, separators=(",", ":"))
    payload_json = json.dumps(zip_payload, separators=(",", ":"))
    summary_json = json.dumps(year_summary, separators=(",", ":"))
    top_json = json.dumps(overall_top)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Texas RMA Longitudinal Geospatial Analysis</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
html, body, #map {{ height:100%; margin:0; }}
body {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:#0f172a; }}
#map {{ background:#e2e8f0; }}
.sr-only {{ position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }}
.card {{
  position:absolute; z-index:1000; background:rgba(255,255,255,.97);
  border:1px solid rgba(15,23,42,.12); border-radius:12px;
  box-shadow:0 12px 30px rgba(15,23,42,.14); box-sizing:border-box;
}}
#title {{
  top:12px; left:50%; transform:translateX(-50%); width:min(720px,calc(100vw - 24px));
  padding:11px 16px; text-align:center; pointer-events:none;
}}
#title .main {{ font-size:17px; font-weight:800; letter-spacing:-.02em; }}
#title .sub {{ margin-top:2px; color:#64748b; font-size:11px; }}
#timeline {{
  top:78px; left:50%; transform:translateX(-50%); display:flex; gap:5px;
  padding:6px; max-width:calc(100vw - 24px);
}}
.year-btn {{
  border:1px solid #cbd5e1; background:#fff; border-radius:8px; padding:6px 10px;
  cursor:pointer; font-weight:700; font-size:12px; color:#334155;
}}
.year-btn.active {{ background:#0f172a; color:#fff; border-color:#0f172a; }}
.year-btn:focus-visible, button:focus-visible, input:focus-visible {{
  outline:3px solid rgba(37,99,235,.35); outline-offset:2px;
}}
#summary {{ top:128px; left:12px; width:245px; padding:12px; }}
.kicker {{ font-size:10px; text-transform:uppercase; letter-spacing:.08em; color:#64748b; font-weight:800; }}
.summary-year {{ font-size:22px; font-weight:850; margin:2px 0 8px; }}
.stat-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:7px; }}
.stat {{ background:#f8fafc; border-radius:8px; padding:7px; }}
.stat .v {{ font-size:15px; font-weight:800; }}
.stat .l {{ font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:.04em; }}
.topline {{ margin-top:8px; padding-top:8px; border-top:1px solid #e2e8f0; font-size:11px; line-height:1.45; }}
#controls {{ top:128px; right:12px; width:240px; padding:12px; }}
#controls h4, #ranking h4, #legend h4, #guide h4 {{ margin:0 0 8px; font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:#475569; }}
.control-row {{ margin:7px 0; font-size:12px; }}
.control-row label {{ display:block; margin:5px 0; cursor:pointer; }}
.search-row {{ display:flex; gap:6px; margin-top:8px; }}
.search-row input {{ min-width:0; flex:1; border:1px solid #cbd5e1; border-radius:8px; padding:7px 8px; font-size:12px; }}
.btn {{
  border:1px solid #cbd5e1; background:#fff; border-radius:8px; padding:7px 9px; cursor:pointer;
  font-size:11px; font-weight:700; color:#334155;
}}
.btn:hover {{ background:#f8fafc; }}
#search-msg {{ min-height:15px; color:#b91c1c; font-size:10px; margin-top:4px; }}
.divider {{ height:1px; background:#e2e8f0; margin:9px 0; }}
#ranking {{ bottom:14px; left:12px; width:245px; padding:12px; max-height:250px; overflow:auto; }}
.rank-tabs {{ display:flex; gap:5px; margin-bottom:8px; }}
.rank-tabs button {{ flex:1; }}
.rank-list {{ font-size:11px; }}
.rank-item {{ display:grid; grid-template-columns:20px 1fr auto; gap:5px; padding:4px 0; border-bottom:1px solid #f1f5f9; }}
#legend {{ bottom:14px; right:12px; width:230px; padding:12px; }}
.legend-row {{ display:flex; align-items:center; gap:7px; margin:4px 0; font-size:10px; }}
.swatch {{ width:15px; height:15px; border-radius:3px; border:1px solid rgba(15,23,42,.15); flex:0 0 15px; }}
#guide {{
  display:none; top:382px; right:12px; width:360px; max-width:calc(100vw - 24px);
  padding:14px; max-height:calc(100vh - 400px); overflow:auto;
}}
#guide.open {{ display:block; }}
#guide p, #guide li {{ font-size:11px; line-height:1.5; color:#334155; }}
#guide ul {{ padding-left:18px; }}
.guide-head {{ display:flex; justify-content:space-between; gap:10px; align-items:center; }}
.guide-close {{ border:0; background:transparent; font-size:20px; cursor:pointer; color:#64748b; }}
.leaflet-tooltip.rma-tip {{
  background:rgba(255,255,255,.98); border:1px solid rgba(15,23,42,.15);
  border-radius:10px; box-shadow:0 12px 30px rgba(15,23,42,.18);
  padding:0; max-width:min(380px,calc(100vw - 24px)); white-space:normal;
}}
.tip {{
  padding:10px 12px;
  min-width:250px;
  max-height:min(520px,calc(100vh - 48px));
  overflow-y:auto;
  box-sizing:border-box;
}}
.tip-head {{ display:flex; justify-content:space-between; gap:14px; border-bottom:1px solid #e2e8f0; padding-bottom:6px; margin-bottom:6px; }}
.tip-zip {{ font-size:16px; font-weight:850; }}
.tip-place {{ color:#64748b; font-size:10px; }}
.tip-year {{ font-weight:800; font-size:11px; color:#475569; }}
.tip-grid {{ display:grid; grid-template-columns:1fr auto; gap:3px 12px; font-size:11px; }}
.tip-grid .label {{ color:#64748b; }}
.tip-grid .value {{ font-weight:750; text-align:right; }}
.tip-sub {{ margin-top:7px; padding-top:7px; border-top:1px solid #e2e8f0; font-size:10px; }}
.popup {{ min-width:290px; max-width:360px; }}
.popup h3 {{ margin:0 0 2px; font-size:16px; }}
.popup .meta {{ color:#64748b; font-size:11px; margin-bottom:8px; }}
.trend-row {{ display:grid; grid-template-columns:42px 1fr 48px; gap:6px; align-items:center; margin:4px 0; font-size:10px; }}
.bar-bg {{ height:7px; border-radius:99px; background:#e2e8f0; overflow:hidden; }}
.bar {{ height:100%; background:#475569; border-radius:99px; }}
.popup-section {{ border-top:1px solid #e2e8f0; margin-top:8px; padding-top:8px; }}
.popup-section strong {{ font-size:10px; text-transform:uppercase; letter-spacing:.05em; color:#475569; }}
.country-list {{ max-height:220px; overflow-y:auto; padding-right:4px; margin-top:5px; }}
@media (max-width:760px) {{
  #title .sub {{ display:none; }}
  #timeline {{ top:66px; overflow-x:auto; }}
  .year-btn {{ padding:5px 8px; }}
  #summary {{ top:112px; width:205px; }}
  #controls {{ top:112px; width:205px; }}
  #ranking {{ display:none; }}
  #legend {{ width:190px; }}
  #guide {{ top:335px; width:calc(100vw - 24px); max-height:45vh; }}
}}
@media (max-width:520px) {{
  #summary {{ display:none; }}
  #controls {{ left:8px; right:auto; top:108px; width:190px; }}
  #legend {{ right:8px; bottom:8px; width:174px; }}
}}
</style>
</head>
<body>
<div id="map"></div>

<div id="title" class="card">
  <div class="main">Texas Refugee Medical Assistance — Longitudinal Geospatial Analysis</div>
  <div class="sub">Synthetic ZIP-level enrollment and country-of-origin patterns · FY2019–FY2024</div>
</div>

<div id="timeline" class="card" role="group" aria-label="Select fiscal year">
  <button type="button" class="year-btn" data-year="2019" aria-pressed="false">FY19</button>
  <button type="button" class="year-btn" data-year="2020" aria-pressed="false">FY20</button>
  <button type="button" class="year-btn" data-year="2021" aria-pressed="false">FY21</button>
  <button type="button" class="year-btn" data-year="2022" aria-pressed="false">FY22</button>
  <button type="button" class="year-btn" data-year="2023" aria-pressed="false">FY23</button>
  <button type="button" class="year-btn active" data-year="2024" aria-pressed="true">FY24</button>
</div>

<div id="summary" class="card" aria-live="polite"></div>

<div id="controls" class="card">
  <h4>Map controls</h4>
  <div class="control-row" role="group" aria-label="Map display mode">
    <label><input type="radio" name="mode" value="enrollment" checked> Enrollment intensity</label>
    <label><input type="radio" name="mode" value="country"> Dominant country of origin</label>
  </div>
  <div class="divider"></div>
  <label for="zip-search" class="sr-only">Search by five-digit ZIP code</label>
  <div class="search-row">
    <input id="zip-search" inputmode="numeric" maxlength="5" autocomplete="postal-code" aria-describedby="search-msg" placeholder="ZIP code">
    <button id="search-btn" class="btn" type="button">Find</button>
  </div>
  <div id="search-msg" aria-live="polite"></div>
  <div class="search-row">
    <button id="reset-btn" class="btn" type="button">Reset view</button>
    <button id="guide-btn" class="btn" type="button" aria-expanded="false" aria-controls="guide">? Map guide</button>
  </div>
</div>

<div id="ranking" class="card">
  <h4>At-a-glance rankings</h4>
  <div class="rank-tabs">
    <button id="cities-tab" class="btn" type="button" aria-pressed="true">Cities</button>
    <button id="countries-tab" class="btn" type="button" aria-pressed="false">Countries</button>
  </div>
  <div id="rank-list" class="rank-list" aria-live="polite"></div>
</div>

<div id="legend" class="card"></div>

<div id="guide" class="card" role="dialog" aria-labelledby="guide-title" aria-hidden="true">
  <div class="guide-head">
    <h4 id="guide-title">Map Guide</h4>
    <button id="guide-close" class="guide-close" aria-label="Close map guide">×</button>
  </div>
  <p><strong>Timeline:</strong> Select FY2019–FY2024 to update the entire map, statewide summary, rankings, tooltips, and legend.</p>
  <p><strong>Enrollment intensity:</strong> Uses fixed enrollment ranges so the same shade means the same absolute range in every fiscal year. This makes year-to-year geographic comparison more meaningful.</p>
  <p><strong>Dominant country:</strong> Colors each active ZIP by the country of origin with the largest enrollment count in that ZIP-year. The ten largest countries across the full six-year dataset receive distinct colors; all others are grouped as Other.</p>
  <p><strong>ZIP details:</strong> Hover for the selected-year snapshot. Click a ZIP for its six-year trend and selected-year country composition.</p>
  <ul>
    <li><strong>YoY</strong> means year-over-year percentage change from the prior fiscal year.</li>
    <li>Large percentages can occur when the prior-year enrollment base is small.</li>
    <li>Cumulative enrollment is the sum of annual synthetic enrollment from FY2019 through the selected year.</li>
  </ul>
  <p>All program values in this portfolio project are synthetic and intentionally perturbed.</p>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const geojson = {geometry_json};
const zipData = {payload_json};
const yearSummary = {summary_json};
const topCountriesOverall = {top_json};
const years = [2019,2020,2021,2022,2023,2024];

let currentYear = 2024;
let currentMode = "enrollment";
let rankingMode = "cities";

const enrollmentBins = [
  {{min:1,max:2,label:"1–2",color:"#eff6ff"}},
  {{min:3,max:5,label:"3–5",color:"#dbeafe"}},
  {{min:6,max:15,label:"6–15",color:"#bfdbfe"}},
  {{min:16,max:40,label:"16–40",color:"#93c5fd"}},
  {{min:41,max:100,label:"41–100",color:"#60a5fa"}},
  {{min:101,max:250,label:"101–250",color:"#3b82f6"}},
  {{min:251,max:Infinity,label:"251+",color:"#1d4ed8"}}
];

const palette = ["#2563eb","#ea580c","#16a34a","#dc2626","#7c3aed","#0891b2","#ca8a04","#be185d","#4f46e5","#65a30d"];
const countryColors = {{}};
topCountriesOverall.forEach((c,i)=>countryColors[c]=palette[i]);

function recordFor(zip) {{
  return zipData[zip]?.[String(currentYear)] || null;
}}

function enrollmentColor(v) {{
  if (!v || v <= 0) return "#ffffff";
  for (const b of enrollmentBins) {{
    if (v >= b.min && v <= b.max) return b.color;
  }}
  return enrollmentBins[enrollmentBins.length-1].color;
}}

function featureStyle(feature) {{
  const r = recordFor(feature.properties.zip_code);
  const total = r ? r.total : 0;
  let fill = "#ffffff";
  if (currentMode === "enrollment") {{
    fill = enrollmentColor(total);
  }} else if (total > 0) {{
    fill = countryColors[r.dominant] || "#94a3b8";
  }}
  return {{
    color: total > 0 ? "#64748b" : "#cbd5e1",
    weight: total > 0 ? 0.75 : 0.35,
    fillColor: fill,
    fillOpacity: total > 0 ? 0.78 : 0.18
  }};
}}

function pctLabel(v) {{
  if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
  const sign = v > 0 ? "+" : "";
  return `${{sign}}${{Number(v).toFixed(1)}}%`;
}}

function tipHtml(zip) {{
  const r = recordFor(zip);
  if (!r) return "";
  const tops = (r.topCountries || []).slice(0,5);
  const topText = tops.length
    ? tops.map(x=>`${{x.country}} (${{x.enrollment.toLocaleString()}})`).join("<br>")
    : "No enrollment";
  return `<div class="tip">
    <div class="tip-head">
      <div><div class="tip-zip">ZIP ${{zip}}</div><div class="tip-place">${{r.city}}, ${{r.county}} County</div></div>
      <div class="tip-year">FY${{String(currentYear).slice(-2)}}</div>
    </div>
    <div class="tip-grid">
      <div class="label">Enrollment</div><div class="value">${{r.total.toLocaleString()}}</div>
      <div class="label">Year-over-year</div><div class="value">${{pctLabel(r.yoy)}}</div>
      <div class="label">Change from FY19</div><div class="value">${{pctLabel(r.from2019)}}</div>
      <div class="label">Cumulative FY19–FY${{String(currentYear).slice(-2)}}</div><div class="value">${{r.cumulative.toLocaleString()}}</div>
      <div class="label">Dominant country</div><div class="value">${{r.total ? r.dominant : "—"}}</div>
    </div>
    <div class="tip-sub"><strong>Top countries in selected year</strong><br>${{topText}}</div>
  </div>`;
}}

function popupHtml(zip) {{
  const records = years.map(y => zipData[zip]?.[String(y)] || {{total:0}});
  const selected = recordFor(zip);
  const maxVal = Math.max(1, ...records.map(r=>r.total || 0));
  const trend = years.map((y,i)=>{{
    const v = records[i].total || 0;
    const width = Math.max(v > 0 ? 2 : 0, (v/maxVal)*100);
    return `<div class="trend-row"><span>FY${{String(y).slice(-2)}}</span><div class="bar-bg"><div class="bar" style="width:${{width}}%"></div></div><span style="text-align:right">${{v.toLocaleString()}}</span></div>`;
  }}).join("");
  const countries = (selected.topCountries || []).map(
    x=>`<div style="display:flex;justify-content:space-between;font-size:11px;margin:3px 0"><span>${{x.country}}</span><strong>${{x.enrollment.toLocaleString()}}</strong></div>`
  ).join("") || `<div style="font-size:11px;color:#64748b">No enrollment in selected year.</div>`;

  const selectedStatus = selected.total > 0
    ? `<div style="font-size:11px;margin:5px 0 2px"><strong>${{selected.total.toLocaleString()}}</strong> enrolled in FY${{String(currentYear).slice(-2)}} · YoY ${{pctLabel(selected.yoy)}}</div>`
    : `<div style="font-size:11px;margin:5px 0 2px;color:#64748b"><strong>No enrollment in FY${{String(currentYear).slice(-2)}}</strong></div>`;

  return `<div class="popup">
    <h3>ZIP ${{zip}}</h3>
    <div class="meta">${{selected.city}}, ${{selected.county}} County</div>
    ${{selectedStatus}}
    <div class="popup-section"><strong>Six-year enrollment trend</strong>${{trend}}</div>
    <div class="popup-section">
      <strong>FY${{String(currentYear).slice(-2)}} full country breakdown</strong>
      <div class="country-list">${{countries}}</div>
    </div>
  </div>`;
}}

const map = L.map("map", {{zoomControl:true, preferCanvas:true}}).setView([31,-99],6);
map.getContainer().setAttribute("aria-label", "Interactive Texas ZIP-code map of synthetic Refugee Medical Assistance enrollment from FY2019 through FY2024");
L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
  maxZoom:19,
  attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}}).addTo(map);

function resetTooltipOffset(lyr) {{
  const el = lyr.getTooltip()?.getElement();
  if (!el) return;
  el.style.marginLeft = "";
  el.style.marginTop = "";
}}

function fitOpenTooltip(lyr) {{
  const tooltip = lyr.getTooltip();
  const el = tooltip?.getElement();
  const mapEl = map.getContainer();
  if (!el || !mapEl) return;

  el.style.marginLeft = "";
  el.style.marginTop = "";

  const mapRect = mapEl.getBoundingClientRect();
  const tipRect = el.getBoundingClientRect();
  const pad = 12;

  let dx = 0;
  let dy = 0;

  if (tipRect.left < mapRect.left + pad) {{
    dx += (mapRect.left + pad) - tipRect.left;
  }}
  if (tipRect.right > mapRect.right - pad) {{
    dx -= tipRect.right - (mapRect.right - pad);
  }}
  if (tipRect.top < mapRect.top + pad) {{
    dy += (mapRect.top + pad) - tipRect.top;
  }}
  if (tipRect.bottom > mapRect.bottom - pad) {{
    dy -= tipRect.bottom - (mapRect.bottom - pad);
  }}

  if (dx) el.style.marginLeft = `${{dx}}px`;
  if (dy) el.style.marginTop = `${{dy}}px`;
}}

function scheduleTooltipFit(lyr) {{
  requestAnimationFrame(() => {{
    fitOpenTooltip(lyr);
    requestAnimationFrame(() => fitOpenTooltip(lyr));
  }});
}}

const zipLayers = {{}};
const layer = L.geoJSON(geojson, {{
  style: featureStyle,
  onEachFeature: (feature, lyr) => {{
    const zip = feature.properties.zip_code;
    zipLayers[zip] = lyr;
    lyr.bindTooltip(()=>tipHtml(zip), {{sticky:false,className:"rma-tip",direction:"auto"}});
    lyr.on("tooltipopen", e=>{{
      const r = recordFor(zip);
      if (!r || r.total <= 0) {{
        lyr.closeTooltip();
        return;
      }}
      scheduleTooltipFit(lyr);
    }});
    lyr.on("tooltipclose", ()=>resetTooltipOffset(lyr));
    lyr.on("click", ()=>lyr.bindPopup(popupHtml(zip), {{maxWidth:390}}).openPopup());
    lyr.on("mouseover", ()=>{{
      const r = recordFor(zip);
      if (r && r.total > 0) lyr.setStyle({{weight:2,color:"#0f172a"}});
    }});
    lyr.on("mouseout", ()=>layer.resetStyle(lyr));
  }}
}}).addTo(map);

const initialBounds = layer.getBounds();
map.fitBounds(initialBounds, {{padding:[30,30]}});

function updateSummary() {{
  const s = yearSummary[String(currentYear)];
  document.getElementById("summary").innerHTML = `
    <div class="kicker">Selected fiscal year</div>
    <div class="summary-year">FY${{String(currentYear).slice(-2)}}</div>
    <div class="stat-grid">
      <div class="stat"><div class="v">${{s.total.toLocaleString()}}</div><div class="l">Enrollment</div></div>
      <div class="stat"><div class="v">${{s.activeZips.toLocaleString()}}</div><div class="l">Active ZIPs</div></div>
      <div class="stat"><div class="v">${{s.counties.toLocaleString()}}</div><div class="l">Counties</div></div>
      <div class="stat"><div class="v">${{years.indexOf(currentYear)+1}} / 6</div><div class="l">Timeline</div></div>
    </div>
    <div class="topline"><strong>Top city:</strong> ${{s.topCity}} · ${{s.topCityValue.toLocaleString()}}<br>
    <strong>Top country:</strong> ${{s.topCountry}} · ${{s.topCountryValue.toLocaleString()}}</div>`;
}}

function updateRanking() {{
  const s = yearSummary[String(currentYear)];
  document.getElementById("cities-tab").setAttribute("aria-pressed", String(rankingMode === "cities"));
  document.getElementById("countries-tab").setAttribute("aria-pressed", String(rankingMode === "countries"));
  const data = rankingMode === "cities" ? s.topCities : s.topCountries;
  document.getElementById("rank-list").innerHTML = data.map((x,i)=>
    `<div class="rank-item"><strong>${{i+1}}</strong><span>${{x.name}}</span><strong>${{x.value.toLocaleString()}}</strong></div>`
  ).join("");
}}

function updateLegend() {{
  const el = document.getElementById("legend");
  if (currentMode === "enrollment") {{
    el.innerHTML = `<h4>Enrollment intensity</h4>` +
      enrollmentBins.map(b=>`<div class="legend-row"><span class="swatch" style="background:${{b.color}}"></span><span>${{b.label}}</span></div>`).join("") +
      `<div class="legend-row"><span class="swatch" style="background:#fff"></span><span>No enrollment</span></div>
       <div style="font-size:9px;color:#64748b;margin-top:6px">Fixed ranges are used for direct year-to-year comparison.</div>`;
  }} else {{
    const rows = topCountriesOverall.map(c=>`<div class="legend-row"><span class="swatch" style="background:${{countryColors[c]}}"></span><span>${{c}}</span></div>`).join("");
    el.innerHTML = `<h4>Dominant country</h4>${{rows}}
      <div class="legend-row"><span class="swatch" style="background:#94a3b8"></span><span>Other</span></div>
      <div class="legend-row"><span class="swatch" style="background:#fff"></span><span>No enrollment</span></div>`;
  }}
}}

function refreshMap() {{
  layer.setStyle(featureStyle);
  layer.eachLayer(l=>{{
    const zip = l.feature.properties.zip_code;
    const r = recordFor(zip);
    if (l.isTooltipOpen()) {{
      if (!r || r.total <= 0) l.closeTooltip();
      else l.setTooltipContent(tipHtml(zip));
    }}
    if (l.isPopupOpen()) l.setPopupContent(popupHtml(zip));
  }});
  document.querySelectorAll(".year-btn").forEach(btn=>{{
    const selected = Number(btn.dataset.year) === currentYear;
    btn.classList.toggle("active", selected);
    btn.setAttribute("aria-pressed", String(selected));
  }});
  updateSummary();
  updateRanking();
  updateLegend();
}}

document.querySelectorAll(".year-btn").forEach(btn=>btn.addEventListener("click", ()=>{{
  currentYear = Number(btn.dataset.year);
  refreshMap();
}}));

document.querySelectorAll('input[name="mode"]').forEach(r=>r.addEventListener("change", e=>{{
  currentMode = e.target.value;
  refreshMap();
}}));

document.getElementById("cities-tab").addEventListener("click", ()=>{{rankingMode="cities";updateRanking();}});
document.getElementById("countries-tab").addEventListener("click", ()=>{{rankingMode="countries";updateRanking();}});

function doSearch() {{
  const input = document.getElementById("zip-search");
  const msg = document.getElementById("search-msg");
  const zip = input.value.trim();
  if (!/^\\d{{5}}$/.test(zip)) {{
    msg.textContent = "Enter a five-digit ZIP code.";
    return;
  }}
  const lyr = zipLayers[zip];
  if (!lyr) {{
    msg.textContent = "ZIP code is not represented in this project.";
    return;
  }}
  msg.textContent = "";
  map.fitBounds(lyr.getBounds(), {{padding:[80,80],maxZoom:11}});
  lyr.bindPopup(popupHtml(zip), {{maxWidth:390}}).openPopup();
}}

document.getElementById("search-btn").addEventListener("click", doSearch);
document.getElementById("zip-search").addEventListener("keydown", e=>{{if(e.key==="Enter") doSearch();}});
document.getElementById("reset-btn").addEventListener("click", ()=>map.fitBounds(initialBounds, {{padding:[30,30]}}));

const guide = document.getElementById("guide");
const guideBtn = document.getElementById("guide-btn");
const guideClose = document.getElementById("guide-close");
function setGuide(open, restoreFocus=false) {{
  guide.classList.toggle("open",open);
  guide.setAttribute("aria-hidden",String(!open));
  guideBtn.setAttribute("aria-expanded",String(open));
  if (open) requestAnimationFrame(()=>guideClose.focus());
  else if (restoreFocus) guideBtn.focus();
}}
guideBtn.addEventListener("click",()=>setGuide(!guide.classList.contains("open")));
guideClose.addEventListener("click",()=>setGuide(false,true));
document.addEventListener("keydown",e=>{{
  if(e.key==="Escape" && guide.classList.contains("open")) setGuide(false,true);
}});

refreshMap();
</script>
</body>
</html>"""

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    print(f"Map written to {DOCS / 'index.html'}")


if __name__ == "__main__":
    main()