"""
market_data.py — public data for Heirloom.

- Yahoo Finance (yfinance): ETF price history (free, no key)
- FRED (US Federal Reserve): T-bill rate and inflation (free key)

Every download is saved to data/cache/ so the live demo still works if the
venue Wi-Fi dies. Run `python prefetch.py` before presenting.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

from planner import FUND_LIBRARY

cacheFolder = Path(__file__).parent / "data" / "cache"
cacheFolder.mkdir(parents=True, exist_ok=True)

# Some funds launched after 2008. For crash replays we stand them in with
# older funds that hold similar things (weights of a stock/bond proxy mix).
REPLAY_PROXIES = {
    "VT":  {"SPY": 1.0},
    "AOK": {"SPY": 0.3, "AGG": 0.7},
    "AOM": {"SPY": 0.4, "AGG": 0.6},
    "AOR": {"SPY": 0.6, "AGG": 0.4},
    "BND": {"AGG": 1.0},
    "BIL": {"SHY": 1.0},
}


def getPriceHistory(tickers, startDate, endDate) -> pd.DataFrame:
    """Daily closing prices, one column per ticker. Cache first, then yfinance."""
    cacheName = f"{'_'.join(sorted(tickers))}_{startDate}_{endDate}.csv"
    cachePath = cacheFolder / cacheName
    if cachePath.exists():
        return pd.read_csv(cachePath, index_col=0, parse_dates=True)

    try:
        import yfinance as yf
        downloaded = yf.download(list(tickers), start=startDate, end=endDate,
                                 auto_adjust=True, progress=False)
        if downloaded.empty:
            raise RuntimeError("No price data returned")
    except Exception:
        # Offline: fall back to the newest cached file for the same funds.
        tickerPrefix = "_".join(sorted(tickers)) + "_"
        olderCaches = sorted(path for path in cacheFolder.glob(f"{tickerPrefix}*.csv")
                             if path.name[len(tickerPrefix)].isdigit())
        if olderCaches:
            return pd.read_csv(olderCaches[-1], index_col=0, parse_dates=True)
        raise
    closePrices = downloaded["Close"]
    if isinstance(closePrices, pd.Series):
        closePrices = closePrices.to_frame(name=tickers[0])
    closePrices = closePrices.dropna(how="all").ffill()
    closePrices.to_csv(cachePath)
    return closePrices


def getFundStats(tickers, yearsOfHistory=10) -> pd.DataFrame:
    """Annual return and volatility per fund, from real history where possible."""
    endDate = pd.Timestamp.today().normalize()
    startDate = endDate - pd.DateOffset(years=yearsOfHistory)
    rows = []
    try:
        prices = getPriceHistory(tickers, startDate.date().isoformat(), endDate.date().isoformat())
    except Exception:
        prices = None

    for ticker in tickers:
        fund = FUND_LIBRARY[ticker]
        annualReturn, annualVolatility, source = None, None, "Planning assumption"
        if prices is not None and ticker in prices and prices[ticker].notna().sum() > 250:
            series = prices[ticker].dropna()
            yearsCovered = (series.index[-1] - series.index[0]).days / 365.25
            annualReturn = (series.iloc[-1] / series.iloc[0]) ** (1 / yearsCovered) - 1
            annualVolatility = series.pct_change().std() * np.sqrt(252)
            source = f"Yahoo Finance, last {yearsCovered:.0f} years"
        if annualReturn is None:
            annualReturn = fund["fallbackReturn"]
            annualVolatility = fund["fallbackVolatility"]
        rows.append({"ticker": ticker, "plainName": fund["plainName"],
                     "annualReturn": annualReturn, "annualVolatility": annualVolatility,
                     "source": source})
    return pd.DataFrame(rows).set_index("ticker")


def getCurrentRates() -> dict:
    """Latest 3-month T-bill rate and yearly inflation from FRED."""
    fallback = {"cashRate": 0.035, "inflationRate": 0.03,
                "source": "Planning assumption (add FRED_API_KEY for live data)"}
    apiKey = os.getenv("FRED_API_KEY")
    cachePath = cacheFolder / "fred_rates.csv"
    try:
        if apiKey:
            from fredapi import Fred
            fred = Fred(api_key=apiKey)
            tBillRate = fred.get_series("DTB3").dropna().iloc[-1] / 100
            consumerPrices = fred.get_series("CPIAUCSL").dropna()
            inflationRate = consumerPrices.iloc[-1] / consumerPrices.iloc[-13] - 1
            rates = {"cashRate": float(tBillRate), "inflationRate": float(inflationRate),
                     "source": "FRED (US Federal Reserve), latest release"}
            pd.Series(rates).to_csv(cachePath)
            return rates
        if cachePath.exists():
            cached = pd.read_csv(cachePath, index_col=0).iloc[:, 0]
            return {"cashRate": float(cached["cashRate"]),
                    "inflationRate": float(cached["inflationRate"]),
                    "source": "FRED (cached)"}
    except Exception:
        pass
    return fallback


def expandToReplayTickers(holdings: dict) -> dict:
    """Swap young funds for older look-alikes so 2008 can be replayed."""
    expanded = {}
    for ticker, amount in holdings.items():
        for proxyTicker, weight in REPLAY_PROXIES.get(ticker, {ticker: 1.0}).items():
            expanded[proxyTicker] = expanded.get(proxyTicker, 0) + amount * weight
    return expanded
