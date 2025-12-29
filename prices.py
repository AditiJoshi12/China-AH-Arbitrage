import yfinance as yf
import pandas as pd

def load_prices(A_ticker, H_ticker, start="2016-01-01"):
    A = yf.download(A_ticker, start=start, progress=False)[["Close", "Volume"]]
    H = yf.download(H_ticker, start=start, progress=False)[["Close", "Volume"]]

    if A.empty or H.empty:
        return None

    df = pd.concat([A, H], axis=1, keys=["A", "H"])
    df = df.sort_index().ffill().dropna()

    # flatten columns
    df.columns = [f"{a}_{b}" for a, b, _ in df.columns]

    return df
