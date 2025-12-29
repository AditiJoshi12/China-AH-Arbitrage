# China-AH-Arbitrage
A pipeline for China A/H cross-market pair trading with statistical filtering of companies, dynamic hedge ratio estimation and backtesting using vectorbt and realistic transaction costs. Because shorting China A shares is very expensive, we looks for stocks to long A shares and short H shares. 

## Methodology: 
- Universe Construction and Pair Selection:
    - Used AA Stocks to get AH pairs. Filter them based on liquidity and half life. We have filtered the stocks to have half life <= 20 days.
    - We had initially kept the half life filter to be much longer (180 days) and then applied Engle-Granger and Johansen tests to find cointegrated pairs but half-life of 180 days is too much.
- Hedge Ratio Estimation:
   - Used Kalman Filtering to estimate hedge ratios instead of 1:1 trades.
- Backtested using VectorBT and realistic transaction costs of 100bps on long A share and 60bps on short H share. 
