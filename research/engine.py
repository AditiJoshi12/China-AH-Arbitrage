"""
Universe funnel + pair backtest, driven off the parquet cache.

Signal logic is the same as the notebooks (Kalman hedge ratio, 60d rolling
z-score of the spread, 2.0 entry / 0.5 exit / 3.5 hard stop). What is added
here is (a) an explicit filter funnel with counts at each stage, (b) an FX-
consistent spread, (c) a return series on a defined capital base so Sharpe,
drawdown and turnover are mutually consistent, and (d) a point-in-time variant
of the selection filters so the full-sample selection bias can be measured
rather than assumed.
"""
import os

import numpy as np
import pandas as pd
from pykalman import KalmanFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "data", "cache")

# --- parameters, all in one place -------------------------------------------
STATS_START = "2019-01-01"     # window the notebook computes ADV / half-life on
BT_START    = "2021-01-01"     # backtest window
IS_END      = "2023-12-31"     # in-sample / out-of-sample boundary
ADV_MIN     = 5e7              # local-currency ADV floor, per leg
HALF_LIFE_MAX = 20             # days
MIN_OBS     = 500              # overlapping observations required to trade
Z_WINDOW    = 60
Z_ENTRY, Z_EXIT, Z_STOP = 2.0, 0.5, 3.5
DELTA       = 1e-5             # Kalman transition covariance parameter


# --- data -------------------------------------------------------------------
def load_cache():
    close = pd.read_parquet(os.path.join(CACHE, "close.parquet"))
    volume = pd.read_parquet(os.path.join(CACHE, "volume.parquet"))
    fx = pd.read_parquet(os.path.join(CACHE, "fx.parquet"))["HKD_CNY"]
    pairs = pd.read_csv(os.path.join(CACHE, "pairs_normalised.csv"))
    return close, volume, fx, pairs


def pair_frame(close, volume, fx, a, h, start=None, end=None):
    """Aligned two-leg frame with the H leg also expressed in CNY."""
    if a not in close.columns or h not in close.columns:
        return None
    df = pd.DataFrame({
        "A_Close": close[a], "A_Volume": volume[a],
        "H_Close": close[h], "H_Volume": volume[h],
    }).sort_index()
    df = df.loc[start:end].ffill().dropna()
    if df.empty:
        return None
    df["H_CNY"] = df["H_Close"] * fx.reindex(df.index).ffill().bfill()
    df["premium"] = (df["A_Close"] - df["H_CNY"]) / df["H_CNY"]
    return df


# --- selection statistics ---------------------------------------------------
def half_life(series):
    """OLS half-life of an AR(1) mean reversion, inf if not mean reverting."""
    s = series.dropna()
    d, lag = s.diff().dropna(), s.shift(1).dropna()
    if len(d) < 50:
        return np.inf
    kappa = np.polyfit(lag.loc[d.index], d, 1)[0]
    return -np.log(2) / kappa if kappa < 0 else np.inf


def selection_stats(close, volume, fx, pairs, start=STATS_START, end=None):
    """Per-pair ADV / premium / half-life over [start, end]. `end=None` = full sample."""
    rows = []
    for _, r in pairs.iterrows():
        df = pair_frame(close, volume, fx, r["A"], r["H"], start, end)
        if df is None or len(df) < 2:
            rows.append({"company": r["company"], "A": r["A"], "H": r["H"],
                         "n_obs": 0 if df is None else len(df), "ADV_A": np.nan,
                         "ADV_H": np.nan, "prem_std": np.nan, "half_life": np.nan})
            continue
        rows.append({
            "company": r["company"], "A": r["A"], "H": r["H"], "n_obs": len(df),
            "ADV_A": (df["A_Close"] * df["A_Volume"]).mean(),
            "ADV_H": (df["H_Close"] * df["H_Volume"]).mean(),
            "prem_std": df["premium"].std(),
            "half_life": half_life(df["premium"]),
        })
    return pd.DataFrame(rows)


def funnel(stats, min_obs=MIN_OBS):
    """Apply the filters in order, returning the survivor count at each stage."""
    stages = []
    df = stats.copy()
    stages.append(("scraped A/H pair list", len(df)))

    df = df[df["n_obs"] > 0]
    stages.append((f"both legs have overlapping history since {STATS_START[:4]}", len(df)))

    df = df[df["n_obs"] >= min_obs]
    stages.append((f"at least {min_obs} overlapping observations", len(df)))

    df = df[(df["ADV_A"] > ADV_MIN) & (df["ADV_H"] > ADV_MIN)]
    stages.append((f"ADV > {ADV_MIN:.0e} on both legs", len(df)))

    df = df[df["half_life"] < HALF_LIFE_MAX]
    stages.append((f"premium half-life < {HALF_LIFE_MAX}d", len(df)))
    return df, stages


# --- signal -----------------------------------------------------------------
def kalman_beta(A, H):
    """Causal (filtered, not smoothed) time-varying hedge ratio."""
    n = len(A)
    kf = KalmanFilter(
        n_dim_obs=1, n_dim_state=1,
        transition_matrices=np.array([[1]]),
        observation_matrices=H.values.reshape(n, 1, 1),
        observation_covariance=1.0,
        transition_covariance=DELTA / (1 - DELTA),
        initial_state_mean=0.0, initial_state_covariance=1.0,
    )
    means, _ = kf.filter(A.values)
    return pd.Series(means.flatten(), index=A.index)


def pair_weights(df):
    """
    Target leg weights per unit of gross notional.

    A unit position is long 1 share of A against beta shares of H (in CNY);
    the pair is scaled so |w_A| + |w_H| = 1 whenever a position is open, i.e.
    the capital base is gross notional and there is no implicit leverage.
    """
    A, H = df["A_Close"], df["H_CNY"]
    beta = kalman_beta(A, H)

    spread = A - beta * H
    z = (spread - spread.rolling(Z_WINDOW).mean()) / spread.rolling(Z_WINDOW).std()

    # state machine: enter at |z| > entry, exit at |z| < exit or |z| > stop
    d = np.zeros(len(z))
    zv = z.values
    for i in range(1, len(zv)):
        prev = d[i - 1]
        if np.isnan(zv[i]):
            d[i] = 0.0
        elif prev == 0.0:
            d[i] = 1.0 if zv[i] < -Z_ENTRY else (-1.0 if zv[i] > Z_ENTRY else 0.0)
        else:
            flat = abs(zv[i]) < Z_EXIT or abs(zv[i]) > Z_STOP
            d[i] = 0.0 if flat else prev
    direction = pd.Series(d, index=z.index)

    gross = A.abs() + (beta * H).abs()
    w_A = direction * A / gross
    w_H = -direction * beta * H / gross
    return pd.DataFrame({"beta": beta, "z": z, "direction": direction,
                         "w_A": w_A, "w_H": w_H}).fillna(0.0)


def pair_returns(df, sig):
    """
    Daily gross return, plus per-leg turnover, on the gross-notional capital base.

    Weights decided from the close of t are held from t to t+1, so the return
    series lags the signal by one day and turnover is charged on the same day
    the new weight starts earning.
    """
    held = sig[["w_A", "w_H"]].shift(1).fillna(0.0)
    rA = df["A_Close"].pct_change().fillna(0.0)
    rH = df["H_CNY"].pct_change().fillna(0.0)

    gross_ret = held["w_A"] * rA + held["w_H"] * rH
    turn_A = held["w_A"].diff().abs().fillna(held["w_A"].abs())
    turn_H = held["w_H"].diff().abs().fillna(held["w_H"].abs())
    return pd.DataFrame({"gross_ret": gross_ret, "turn_A": turn_A, "turn_H": turn_H})


def build_book(close, volume, fx, survivors, start=BT_START, end=None):
    """Equal-weight book across the surviving pairs. Returns per-pair panels."""
    panels = {}
    for _, r in survivors.iterrows():
        df = pair_frame(close, volume, fx, r["A"], r["H"], start, end)
        if df is None or len(df) < Z_WINDOW + 30:
            continue
        sig = pair_weights(df)
        if (sig["direction"] != 0).sum() == 0:
            continue
        panels[r["company"]] = pair_returns(df, sig).join(sig[["z", "direction"]])
    return panels


def combine(panels):
    """Equal capital across pairs; a pair only draws capital once it has data."""
    if not panels:
        return None
    gross = pd.concat({k: v["gross_ret"] for k, v in panels.items()}, axis=1)
    tA = pd.concat({k: v["turn_A"] for k, v in panels.items()}, axis=1)
    tH = pd.concat({k: v["turn_H"] for k, v in panels.items()}, axis=1)
    live = gross.notna().sum(axis=1).replace(0, np.nan)
    return pd.DataFrame({
        "gross_ret": gross.sum(axis=1) / live,
        "turn_A": tA.sum(axis=1) / live,
        "turn_H": tH.sum(axis=1) / live,
    }).dropna()


# --- performance ------------------------------------------------------------
def net_returns(book, cost_A_bps, cost_H_bps):
    """Round-trip cost quoted per leg; charged one-way (half) on each weight change."""
    cost = (book["turn_A"] * cost_A_bps / 2 + book["turn_H"] * cost_H_bps / 2) / 1e4
    return book["gross_ret"] - cost


def metrics(gross, net, turn):
    def sharpe(r):
        return np.nan if r.std() == 0 else r.mean() / r.std() * np.sqrt(252)

    equity = (1 + net).cumprod()
    dd = (equity / equity.cummax() - 1).min()
    yrs = len(net) / 252
    return {
        "start": net.index.min().date(), "end": net.index.max().date(),
        "days": len(net), "years": yrs,
        "sharpe_gross": sharpe(gross), "sharpe_net": sharpe(net),
        "max_dd": dd, "total_return": equity.iloc[-1] - 1,
        "ann_return": equity.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan,
        "ann_vol": net.std() * np.sqrt(252),
        "ann_turnover": turn.mean() * 252,
    }
