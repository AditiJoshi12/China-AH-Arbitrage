"""
Produce every number that goes into README.md: filter funnel, headline table,
in-sample / out-of-sample split, cost sensitivity, and the point-in-time
selection check. Writes results/*.csv and results/summary.json.

    python research/run_report.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (ADV_MIN, BT_START, HALF_LIFE_MAX, IS_END, MIN_OBS,      # noqa: E402
                    STATS_START, build_book, combine, load_cache, metrics,
                    net_returns, pair_frame, selection_stats)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
os.makedirs(RESULTS, exist_ok=True)

# round-trip bps per leg: (A-share, H-share). 100/60 is the base case.
COST_GRID = [(0, 0), (25, 15), (50, 30), (100, 60), (150, 90), (200, 120), (300, 180)]
BASE_COST = (100, 60)


def engle_granger(df):
    """ADF on the OLS residual of A on H (CNY). Returns (beta, pvalue)."""
    A, H = df["A_Close"].values, df["H_CNY"].values
    res = sm.OLS(A, sm.add_constant(H)).fit()
    return res.params[1], adfuller(res.resid, autolag="AIC")[1]


def staged_funnel(stats, label):
    """Notebook-order funnel: data -> liquidity -> half-life -> tradeable."""
    rows, df = [], stats.copy()
    rows.append(("scraped A/H pair list", len(df)))
    df = df[df["n_obs"] > 0]
    rows.append(("both legs have price history", len(df)))
    df = df[(df["ADV_A"] > ADV_MIN) & (df["ADV_H"] > ADV_MIN)]
    rows.append((f"ADV > CNY/HKD {ADV_MIN:.0e} on both legs", len(df)))
    df = df[df["half_life"] < HALF_LIFE_MAX]
    rows.append((f"premium half-life < {HALF_LIFE_MAX}d", len(df)))
    df = df[df["n_obs"] >= MIN_OBS]
    rows.append((f">= {MIN_OBS} overlapping observations", len(df)))
    print(f"\n--- funnel [{label}] ---")
    for name, n in rows:
        print(f"{n:5d}  {name}")
    return df, rows


def main():
    close, volume, fx, pairs = load_cache()

    # ---------- 1. selection, full sample (what the notebooks actually do) ----
    stats_full = selection_stats(close, volume, fx, pairs)
    stats_full.to_csv(os.path.join(RESULTS, "selection_stats_full_sample.csv"), index=False)
    surv_full, funnel_full = staged_funnel(stats_full, "full sample")

    # cointegration, reported but NOT applied (the notebook's EG stage kills all)
    liquid = stats_full[(stats_full["ADV_A"] > ADV_MIN) &
                        (stats_full["ADV_H"] > ADV_MIN) &
                        (stats_full["n_obs"] >= MIN_OBS)]
    eg = []
    for _, r in liquid.iterrows():
        df = pair_frame(close, volume, fx, r["A"], r["H"], STATS_START, None)
        if df is None or len(df) < 252:
            continue
        b, p = engle_granger(df)
        eg.append({"company": r["company"], "beta": b, "pvalue": p})
    eg = pd.DataFrame(eg)
    eg.to_csv(os.path.join(RESULTS, "engle_granger_liquid_set.csv"), index=False)
    n_coint = int(((eg["pvalue"] < 0.05) & (eg["beta"] > 0)).sum())
    print(f"\nEngle-Granger on the {len(eg)} liquid pairs: "
          f"{n_coint} pass p<0.05 & beta>0 (stage reported, not applied)")

    # ---------- 2. point-in-time selection at the IS/OOS boundary ------------
    stats_pit = selection_stats(close, volume, fx, pairs, STATS_START, IS_END)
    stats_pit.to_csv(os.path.join(RESULTS, "selection_stats_pit_2023.csv"), index=False)
    surv_pit, funnel_pit = staged_funnel(stats_pit, f"PIT as of {IS_END}")

    print("\nfull-sample survivors:", sorted(surv_full["company"]))
    print("PIT survivors        :", sorted(surv_pit["company"]))

    # ---------- 3. backtest --------------------------------------------------
    panels = build_book(close, volume, fx, surv_full, start=BT_START)
    print(f"\npairs producing trades: {len(panels)} -> {sorted(panels)}")
    book = combine(panels)
    book.to_csv(os.path.join(RESULTS, "book_daily.csv"))

    turn = book["turn_A"] + book["turn_H"]
    windows = {
        "full": book,
        "in_sample": book.loc[:IS_END],
        "out_of_sample": book.loc[pd.Timestamp(IS_END) + pd.Timedelta(days=1):],
    }

    head = []
    for name, b in windows.items():
        net = net_returns(b, *BASE_COST)
        m = metrics(b["gross_ret"], net, b["turn_A"] + b["turn_H"])
        m["window"] = name
        head.append(m)
    head = pd.DataFrame(head).set_index("window")
    head.to_csv(os.path.join(RESULTS, "headline.csv"))
    print("\n--- headline (costs 100/60 bps round trip) ---")
    print(head[["start", "end", "days", "sharpe_gross", "sharpe_net",
                "max_dd", "total_return", "ann_turnover"]].to_string())

    # per-pair, so the concentration is visible
    per_pair = []
    for name, p in panels.items():
        net = net_returns(p, *BASE_COST)
        m = metrics(p["gross_ret"], net, p["turn_A"] + p["turn_H"])
        m["pair"] = name
        m["round_trips"] = int((p["direction"].diff().abs() > 0).sum() / 2)
        per_pair.append(m)
    per_pair = pd.DataFrame(per_pair).set_index("pair")
    per_pair.to_csv(os.path.join(RESULTS, "per_pair.csv"))
    print("\n--- per pair ---")
    print(per_pair[["start", "end", "sharpe_gross", "sharpe_net", "max_dd",
                    "total_return", "ann_turnover", "round_trips"]].to_string())

    # ---------- 3b. the honest counterfactual --------------------------------
    # Select using only data available at IS_END, then trade the OOS window.
    # This is the same strategy with the full-sample look-ahead removed.
    pit_panels = build_book(close, volume, fx, surv_pit,
                            start=str(pd.Timestamp(IS_END).date()))
    pit_book = combine(pit_panels)
    pit_rows = []
    if pit_book is not None:
        pit_net = net_returns(pit_book, *BASE_COST)
        m = metrics(pit_book["gross_ret"], pit_net,
                    pit_book["turn_A"] + pit_book["turn_H"])
        m["book"] = "PIT-selected, OOS only"
        pit_rows.append(m)
        for name, p in pit_panels.items():
            n2 = net_returns(p, *BASE_COST)
            mm = metrics(p["gross_ret"], n2, p["turn_A"] + p["turn_H"])
            mm["book"] = name
            pit_rows.append(mm)
        pit_book.to_csv(os.path.join(RESULTS, "pit_book_daily.csv"))
    pit_df = pd.DataFrame(pit_rows).set_index("book")
    pit_df.to_csv(os.path.join(RESULTS, "pit_book_oos.csv"))
    print("\n--- point-in-time selected book, OOS window only ---")
    print(pit_df[["start", "end", "sharpe_gross", "sharpe_net", "max_dd",
                  "total_return", "ann_turnover"]].to_string())

    # ---------- 4. cost sensitivity -----------------------------------------
    sens = []
    for cA, cH in COST_GRID:
        row = {"cost_A_bps": cA, "cost_H_bps": cH}
        for name, b in windows.items():
            net = net_returns(b, cA, cH)
            row[f"sharpe_{name}"] = (np.nan if net.std() == 0
                                     else net.mean() / net.std() * np.sqrt(252))
            row[f"totret_{name}"] = (1 + net).cumprod().iloc[-1] - 1
        sens.append(row)
    sens = pd.DataFrame(sens)
    sens.to_csv(os.path.join(RESULTS, "cost_sensitivity.csv"), index=False)
    print("\n--- cost sensitivity (round-trip bps per leg) ---")
    print(sens.to_string(index=False))

    # breakeven cost, holding the 100:60 A:H ratio
    def sharpe_at(mult, b):
        net = net_returns(b, 100 * mult, 60 * mult)
        return net.mean() / net.std() * np.sqrt(252)

    be = {}
    for name, b in windows.items():
        lo, hi = 0.0, 40.0
        if sharpe_at(hi, b) > 0:
            be[name] = None
        else:
            for _ in range(60):
                mid = (lo + hi) / 2
                if sharpe_at(mid, b) > 0:
                    lo = mid
                else:
                    hi = mid
            be[name] = round(100 * lo, 1)
    print("\nbreakeven A-leg round-trip cost (H held at 0.6x), bps:", be)

    summary = {
        "funnel_full_sample": funnel_full,
        "funnel_pit": funnel_pit,
        "survivors_full": sorted(surv_full["company"].tolist()),
        "survivors_pit": sorted(surv_pit["company"].tolist()),
        "traded_pairs": sorted(panels),
        "eg_liquid_tested": len(eg), "eg_pass": n_coint,
        "breakeven_A_bps": be,
        "pit_book_oos": json.loads(pit_df.reset_index().to_json(orient="records")),
        "headline": json.loads(head.reset_index().to_json(orient="records")),
        "per_pair": json.loads(per_pair.reset_index().to_json(orient="records")),
        "cost_sensitivity": json.loads(sens.to_json(orient="records")),
    }
    with open(os.path.join(RESULTS, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nwrote {RESULTS}")


if __name__ == "__main__":
    sys.exit(main())
