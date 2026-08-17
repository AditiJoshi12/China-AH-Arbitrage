"""
Download and cache prices for the full A/H pair list, plus FX.

Everything downstream (universe funnel, backtest, report) reads from the cache
so the numbers are reproducible without re-hitting Yahoo.

    python research/build_cache.py
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
os.makedirs(CACHE, exist_ok=True)

START = "2016-01-01"
CHUNK = 40


def pair_list():
    """The scraped A/H list, ticker-normalised the same way the notebook does."""
    pairs = pd.read_csv(os.path.join(DATA, "ah_pairs.csv"))
    pairs["A_Share"] = pairs["A_Share"].str.replace(".SH", ".SS", regex=False)
    pairs["H_Share"] = pairs["H_Share"].str[1:]      # 00038.HK -> 0038.HK
    pairs = pairs.rename(columns={"Name": "company", "A_Share": "A", "H_Share": "H"})
    return pairs[["company", "A", "H"]]


def download(tickers, field):
    """Batch download one field for a list of tickers -> wide DataFrame."""
    out = {}
    for i in range(0, len(tickers), CHUNK):
        batch = tickers[i:i + CHUNK]
        print(f"  {field} {i + 1}-{i + len(batch)} / {len(tickers)}", flush=True)
        for attempt in range(3):
            try:
                df = yf.download(batch, start=START, progress=False,
                                 auto_adjust=True, threads=True)
                break
            except Exception as e:                      # noqa: BLE001
                print(f"    retry {attempt + 1}: {e}", flush=True)
                time.sleep(5)
        else:
            continue

        if isinstance(df.columns, pd.MultiIndex):
            if field not in df.columns.get_level_values(0):
                continue
            sub = df[field]
        else:
            sub = df[[field]].rename(columns={field: batch[0]})

        for t in sub.columns:
            s = sub[t].dropna()
            if len(s):
                out[t] = s
        time.sleep(1)

    return pd.DataFrame(out).sort_index()


def main():
    pairs = pair_list()
    pairs.to_csv(os.path.join(CACHE, "pairs_normalised.csv"), index=False)
    tickers = sorted(set(pairs["A"]).union(pairs["H"]))
    print(f"{len(pairs)} pairs, {len(tickers)} unique tickers")

    close = download(tickers, "Close")
    volume = download(tickers, "Volume")
    close.to_parquet(os.path.join(CACHE, "close.parquet"))
    volume.to_parquet(os.path.join(CACHE, "volume.parquet"))

    fx = yf.download(["USDCNY=X", "USDHKD=X"], start=START,
                     progress=False, auto_adjust=True)["Close"]
    # HKD -> CNY multiplier
    hkd_cny = (fx["USDCNY=X"] / fx["USDHKD=X"]).dropna().rename("HKD_CNY")
    hkd_cny.to_frame().to_parquet(os.path.join(CACHE, "fx.parquet"))

    print(f"\nclose  {close.shape}  {close.index.min().date()} -> {close.index.max().date()}")
    print(f"volume {volume.shape}")
    print(f"fx     {hkd_cny.shape}")
    print(f"tickers with no data: {sorted(set(tickers) - set(close.columns))}")


if __name__ == "__main__":
    sys.exit(main())
