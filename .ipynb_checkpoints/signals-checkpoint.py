import pandas as pd

def compute_spread_z(A, H, beta, window=60):
    spread = A - beta * H
    mu = spread.rolling(window).mean()
    sigma = spread.rolling(window).std()
    z = (spread - mu) / sigma
    return spread, z


def generate_signals(z, entry=2.0, exit=0.5):
    long_entries = z < -entry
    short_entries = z > entry

    long_exits = z > -exit
    short_exits = z < exit

    entries = long_entries | short_entries
    exits = long_exits | short_exits

    direction = pd.Series(0, index=z.index)
    direction[long_entries] = 1
    direction[short_entries] = -1

    return entries, exits, direction