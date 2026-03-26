#!/usr/bin/env python3
"""
Reproducible econometric pipeline for:
"Should India follow an export-led growth strategy in the 21st century?"

Data sources:
- World Bank WDI API
- UN Comtrade API (optional: requires internet and may rate-limit)
- RBI/CMIE local CSV drops (user-provided)

Outputs:
- processed datasets
- regression tables
- publication-quality figures
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
import statsmodels.formula.api as smf
from linearmodels.iv import IV2SLS
import matplotlib.pyplot as plt
import seaborn as sns


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"
TAB = ROOT / "tables"

for d in [RAW, PROC, FIG, TAB]:
    d.mkdir(parents=True, exist_ok=True)


def fetch_wdi(indicators: Dict[str, str], country: str = "IN", start: int = 2000, end: int = 2024) -> pd.DataFrame:
    """Fetch annual WDI indicator data for India."""
    rows: List[pd.DataFrame] = []
    for name, code in indicators.items():
        url = (
            f"https://api.worldbank.org/v2/country/{country}/indicator/{code}"
            f"?format=json&per_page=2000&date={start}:{end}"
        )
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        payload = r.json()
        if len(payload) < 2:
            continue
        df = pd.DataFrame(payload[1])
        if df.empty:
            continue
        df = df[["date", "value"]].rename(columns={"date": "year", "value": name})
        df["year"] = df["year"].astype(int)
        rows.append(df)

    if not rows:
        raise RuntimeError("No WDI data downloaded. Check internet/API availability.")

    out = rows[0]
    for add in rows[1:]:
        out = out.merge(add, on="year", how="outer")
    out = out.sort_values("year").reset_index(drop=True)
    return out


def load_local_optional() -> pd.DataFrame:
    """Load optional local RBI/CMIE exports if present."""
    files = {
        "rbi": RAW / "rbi_macro.csv",
        "cmie": RAW / "cmie_state_panel.csv",
    }
    found = {k: p for k, p in files.items() if p.exists()}
    if not found:
        return pd.DataFrame()

    frames = []
    for src, path in found.items():
        df = pd.read_csv(path)
        df["source"] = src
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def build_national_dataset() -> pd.DataFrame:
    indicators = {
        "gdp_growth": "NY.GDP.MKTP.KD.ZG",
        "exports_gs_gdp": "NE.EXP.GNFS.ZS",
        "gcf_gdp": "NE.GDI.TOTL.ZS",
        "inflation_cpi": "FP.CPI.TOTL.ZG",
        "manufacturing_va_growth": "NV.IND.MANF.KD.ZG",
    }
    df = fetch_wdi(indicators)

    # Proxy for export growth when value series not directly available
    df["exports_growth_proxy"] = df["exports_gs_gdp"].pct_change() * 100

    # Deterministic missing handling
    for col in [c for c in df.columns if c != "year"]:
        df[col] = df[col].interpolate(limit_direction="both")

    df.to_csv(PROC / "india_national_2000_2024.csv", index=False)
    return df


def run_baseline_ols(df: pd.DataFrame):
    reg_df = df.dropna(subset=["gdp_growth", "exports_growth_proxy", "gcf_gdp", "inflation_cpi"]).copy()
    formula = "gdp_growth ~ exports_growth_proxy + gcf_gdp + inflation_cpi"
    m = smf.ols(formula=formula, data=reg_df).fit(cov_type="HC3")
    with open(TAB / "ols_summary.txt", "w", encoding="utf-8") as f:
        f.write(m.summary().as_text())

    coef = pd.DataFrame({"term": m.params.index, "coef": m.params.values, "pvalue": m.pvalues.values})
    coef.to_csv(TAB / "ols_coefficients.csv", index=False)
    return m


def synthetic_panel_from_national(df: pd.DataFrame, states: int = 20) -> pd.DataFrame:
    """
    Build a synthetic state panel for pipeline demonstration when state data is unavailable.
    Replace with real state-level data from CMIE/RBI/Comtrade merges.
    """
    rng = np.random.default_rng(42)
    state_names = [f"S{str(i).zfill(2)}" for i in range(1, states + 1)]
    panel = []
    for s in state_names:
        s_fe = rng.normal(0, 1)
        for _, r in df.iterrows():
            yr = int(r["year"])
            export_g = float(r["exports_growth_proxy"] + rng.normal(0, 2))
            inv = float(r["gcf_gdp"] + rng.normal(0, 1.5))
            demand_shock = rng.normal(0, 1)
            growth = 2.0 + 0.15 * export_g + 0.08 * inv + s_fe + rng.normal(0, 1.5)
            mfg_emp_g = 0.5 + 0.10 * export_g + 0.03 * inv + rng.normal(0, 1.2)
            panel.append(
                {
                    "state": s,
                    "year": yr,
                    "export_growth": export_g,
                    "investment_rate": inv,
                    "global_demand_shock": demand_shock,
                    "gdp_growth": growth,
                    "mfg_emp_growth": mfg_emp_g,
                }
            )
    out = pd.DataFrame(panel)
    out.to_csv(PROC / "india_state_panel_synthetic.csv", index=False)
    return out


def run_fixed_effects(panel: pd.DataFrame):
    panel = panel.copy()
    panel["state"] = panel["state"].astype("category")
    formula = "gdp_growth ~ export_growth + investment_rate + C(state) + C(year)"
    fe = smf.ols(formula=formula, data=panel).fit(cov_type="cluster", cov_kwds={"groups": panel["state"]})
    with open(TAB / "fe_summary.txt", "w", encoding="utf-8") as f:
        f.write(fe.summary().as_text())
    return fe


def run_iv(panel: pd.DataFrame):
    iv_df = panel.dropna().copy()
    iv_df = iv_df.set_index(["state", "year"])
    exog = sm.add_constant(iv_df[["investment_rate"]])
    endog = iv_df["export_growth"]
    instr = iv_df[["global_demand_shock"]]
    dep = iv_df["gdp_growth"]

    model = IV2SLS(dep, exog, endog, instr).fit(cov_type="robust")
    with open(TAB / "iv_summary.txt", "w", encoding="utf-8") as f:
        f.write(str(model.summary))
    return model


def plot_series(df: pd.DataFrame):
    sns.set_theme(style="whitegrid", context="talk")
    plt.figure(figsize=(12, 7), dpi=320)
    plt.plot(df["year"], df["gdp_growth"], label="GDP growth (%)", linewidth=2.5)
    plt.plot(df["year"], df["exports_growth_proxy"], label="Export growth proxy (%)", linewidth=2.5)
    plt.title("India: Export Growth vs GDP Growth")
    plt.xlabel("Year")
    plt.ylabel("Percent")
    plt.legend(frameon=False)
    plt.tight_layout()
    plt.savefig(FIG / "export_vs_gdp_timeseries.png")
    plt.close()


def plot_scatter(panel: pd.DataFrame):
    plt.figure(figsize=(11, 7), dpi=320)
    sns.regplot(data=panel, x="export_growth", y="mfg_emp_growth", scatter_kws={"alpha": 0.35, "s": 20})
    plt.title("Export Growth and Manufacturing Employment Growth")
    plt.xlabel("Export Growth (%)")
    plt.ylabel("Manufacturing Employment Growth (%)")
    plt.tight_layout()
    plt.savefig(FIG / "exports_vs_employment_scatter.png")
    plt.close()


def plot_event_study(df: pd.DataFrame, shock_year: int = 2020, window: int = 5):
    d = df.copy()
    d["event_time"] = d["year"] - shock_year
    d = d[(d["event_time"] >= -window) & (d["event_time"] <= window)]

    plt.figure(figsize=(10, 6), dpi=320)
    plt.axvline(0, linestyle="--", color="black", linewidth=1)
    plt.plot(d["event_time"], d["gdp_growth"], marker="o", label="GDP growth")
    plt.plot(d["event_time"], d["exports_growth_proxy"], marker="s", label="Export growth proxy")
    plt.title(f"Event Study Around {shock_year} Shock")
    plt.xlabel("Years relative to shock")
    plt.ylabel("Percent")
    plt.legend(frameon=False)
    plt.tight_layout()
    plt.savefig(FIG / "event_study_shock.png")
    plt.close()


def plot_heatmap(panel: pd.DataFrame):
    pivot = panel.pivot_table(index="state", columns="year", values="export_growth", aggfunc="mean")
    plt.figure(figsize=(14, 8), dpi=320)
    sns.heatmap(pivot, cmap="viridis", cbar_kws={"label": "Export growth (%)"})
    plt.title("State-wise Export Intensity (Proxy) Heatmap")
    plt.xlabel("Year")
    plt.ylabel("State")
    plt.tight_layout()
    plt.savefig(FIG / "state_export_intensity_heatmap.png")
    plt.close()


def main():
    national = build_national_dataset()
    ols = run_baseline_ols(national)

    local_optional = load_local_optional()
    if local_optional.empty:
        panel = synthetic_panel_from_national(national)
        panel_note = "Synthetic panel used because local CMIE/RBI state panel files were not found."
    else:
        # Placeholder: user should map local schema to required columns before FE/IV.
        panel = local_optional.copy()
        panel_note = "Local optional panel detected; ensure schema matches required fields."

    fe = run_fixed_effects(panel)
    iv = run_iv(panel)

    plot_series(national)
    plot_scatter(panel)
    plot_event_study(national)
    plot_heatmap(panel)

    summary = {
        "ols_export_coef": float(ols.params.get("exports_growth_proxy", np.nan)),
        "fe_export_coef": float(fe.params.get("export_growth", np.nan)),
        "iv_export_coef": float(iv.params.get("export_growth", np.nan)),
        "panel_note": panel_note,
    }
    with open(TAB / "model_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Pipeline complete.")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
