# Results

*China A/H mean-reversion pair trade — Kalman hedge ratio, 60d rolling z-score, 2σ entry / 0.5σ exit / 3.5σ hard stop, on a two-name book selected from the scraped Hang Seng A/H list. Backtest 2021-01-04 → 2026-08-17.*

Read this section together with the two caveats at the bottom — they're the difference between "1.22 in-sample Sharpe" and "an edge you would have captured with a real trading account".

## Universe funnel

The scraped list has 150 A/H pairs. Two survive the filters actually applied, both computed on **the full sample** (see caveat 1):

| stage | pairs remaining |
|---|---:|
| scraped A/H pair list | 150 |
| both legs have price history since 2019 | 150 |
| ADV > CNY / HKD 5×10⁷ on both legs | 86 |
| premium half-life < 20d | **2** |
| ≥ 500 overlapping observations (final traded set) | **2** |

Survivors: **HAIER SMARTHOME** (600690.SS / 6690.HK) and **CTG DUTY-FREE** (601888.SS / 1880.HK).

The Engle-Granger cointegration test is *computed* (46 of the 86 liquid pairs pass p<0.05 with a positive hedge ratio) but not *applied* — with the ≤20-day half-life gate above it, EG doesn't tighten the set further. Both traded pairs pass EG anyway (Haier p ≈ 2×10⁻⁵, CTG p ≈ 1×10⁻⁸).

## Headline

All Sharpes annualised. Costs are round-trip bps *per leg*: 100 bps on the A-share leg (mainland-China stamp duty + commission + slippage), 60 bps on the H-share leg. Return series is on gross-notional capital (a unit position holds A against β·H in CNY and is scaled so |wA|+|wH|=1), so Sharpe, drawdown, and turnover are on the same base.

| window | days | gross Sharpe | **net Sharpe** | max DD | total return | ann. turnover (× gross) |
|---|---:|---:|---:|---:|---:|---:|
| Full (2021-01 → 2026-08) | 1,422 | 1.24 | 0.39 | −10.5% | +13.4% | 13.9 |
| **In-sample** (2021-01 → 2023-12) | 759 | 2.12 | **1.22** | −1.9% | +18.9% | 11.9 |
| **Out-of-sample** (2024-01 → 2026-08) | 663 | 0.64 | **−0.20** | −10.5% | −4.6% | 16.2 |

**The OOS number is the one that matters.** A net Sharpe of −0.20 out-of-sample, on a book selected with future information (see caveat 1), is not a viable strategy — it's a warning that the in-sample 1.22 is a selection artifact. The gross OOS Sharpe of 0.64 says the signal is directionally alive; costs eat it.

Per-pair, the OOS deterioration is concentrated in CTG DUTY-FREE (started 2022-08, gross 0.20 / net −0.23 over its life) with Haier bleeding down from IS gross 2.14 / net 1.23 to OOS gross 1.46 / net 0.27. Haier alone is the only pair that survives costs on any horizon.

## Cost sensitivity

The base case is 100/60 bps round-trip per leg. Sharpe at each grid point:

| A-leg (rt bps) | H-leg (rt bps) | full | in-sample | **out-of-sample** |
|---:|---:|---:|---:|---:|
| 0 | 0 | 1.24 | 2.12 | **0.64** |
| 25 | 15 | 1.03 | 1.91 | **0.43** |
| 50 | 30 | 0.82 | 1.69 | **0.23** |
| **100** | **60** | **0.39** | **1.22** | **−0.20** |
| 150 | 90 | −0.06 | 0.72 | **−0.62** |
| 200 | 120 | −0.50 | 0.23 | **−1.05** |
| 300 | 180 | −1.32 | −0.69 | **−1.85** |

Breakeven A-leg round-trip cost (holding H at 0.6× the A cost): **~144 bps full sample, ~223 bps in-sample, ~77 bps out-of-sample**. The OOS breakeven sits below the base cost assumption — with A-share round-trip costs on the order of 100 bps for a small book (10 bps stamp duty on sells + 3–5 bps commission per side + realistic bid-ask crossing), there is no margin. Turnover ~14× gross a year means every extra 10 bps of round-trip cost shifts net Sharpe by roughly 0.2–0.3 units.

## Equity curve

Three lines, one y-axis, IS/OOS divider dashed:

![Equity curves](equity_curve.svg)

* **Gross** (blue) — full-sample-selected book before costs.
* **Net 100/60 bps** (orange) — same book after costs. The IS run compounds cleanly; the OOS run drifts sideways then rolls over.
* **Net, PIT-selected** (green) — the honest counterfactual. Universe re-selected using only data available at 2023-12-31 and traded 2024-01-02 forward. This picks a *different* six-name set (China Mobile, SMIC, WuXi AppTec, CPIC, BeOne Medicines, Haier), which run at gross Sharpe 0.54 / **net Sharpe −0.82 / max DD −11.5% / total return −9.5%** over the OOS window. Haier is the one pair that overlaps with the full-sample survivors and is again the only one that survives costs.

## Caveats

Two things a reader should know before mapping these numbers onto any decision:

**1. The ≤20-day half-life filter is computed on the full sample (2019-01 → today), not rolling — and this inflates the in-sample backtest.** A pair only enters the book because we *already know* its premium was mean-reverting over a window that includes the trading period. This is textbook selection bias. To quantify it rather than just note it, I re-ran the filter using only data available at 2023-12-31 (`selection_stats_pit_2023.csv`) and traded the six survivors forward: 6 pairs pass PIT vs 2 pass full-sample, and they are **almost entirely different names** (only Haier overlaps). That PIT-selected book returns **net Sharpe −0.82 / max DD −11.5% over the OOS window**, versus the full-sample-selected book's net Sharpe −0.20 over the same period. The gap is the selection bias, made concrete: the in-sample edge is largely retrospective pair-picking, not signal.

**2. The pair universe was scraped as-of-today, so delisted, acquired, or de-dual-listed pairs are missing (survivorship bias) and every survivor's history is post-listing-only.** The 150 names are today's Hang Seng A/H twins; anything that stopped trading in either market before the scrape date isn't in the file. That biases upward in the usual way (surviving pairs are the ones whose businesses held together over the sample), and it also means selection filters like ADV and half-life run on backfilled histories that a real trader wouldn't have seen day-one. Fixing this properly needs a historical A/H membership snapshot with delisted tickers preserved (SEHK/CSMAR historical constituents); the current file only mitigates by measuring the PIT counterfactual above.

Both caveats push the same way: **the honest number to quote is the PIT-selected OOS Sharpe of −0.82**, not the 1.22 in-sample or the 0.39 full-sample. The pair-trade construction works (gross Sharpe is positive across every cut), but on this universe and cost regime it doesn't survive to net alpha.

## Reproducing

```bash
python research/build_cache.py        # one-off Yahoo download, ~5 min
python research/run_report.py         # funnel, backtest, cost grid, PIT counterfactual
python research/plot_equity.py        # equity_curve.svg
```

All csvs in this directory (`headline.csv`, `per_pair.csv`, `cost_sensitivity.csv`, `pit_book_oos.csv`, `selection_stats_full_sample.csv`, `selection_stats_pit_2023.csv`, `book_daily.csv`, `pit_book_daily.csv`) are regenerated end-to-end from the cached parquet — no manual step in the chain.
