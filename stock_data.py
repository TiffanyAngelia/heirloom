"""
stock_data.py — collects public data on a list of stocks for the AI to analyse.

Sources (from the hackathon brief):
  - Yahoo Finance (yfinance): 5 years of prices → growth, ups and downs, worst fall, dividends
  - Finnhub (free key):        analyst ratings, recent news headlines, valuation and beta
  - SEC EDGAR (no key):        revenue, profit and debt from official annual reports (10-K)
  - FRED (free key):           interest rate and inflation, via market_data.getCurrentRates

Everything is saved to data/cache/ so the demo works offline.
Run `python stock_data.py` to build and save a snapshot.
"""

import json
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

from market_data import getCurrentRates

load_dotenv()

cacheFolder = Path(__file__).parent / "data" / "cache"
cacheFolder.mkdir(parents=True, exist_ok=True)

# A starting list of large, established companies across different industries.
# Steady, dividend-paying businesses suit retirees better than fast-moving tech
# start-ups. Edit freely: the AI only ever picks from this list.
CANDIDATE_STOCKS = {
    "JNJ": "Healthcare", "UNH": "Healthcare", "ABBV": "Healthcare",
    "PG": "Household goods", "KO": "Food & drink", "PEP": "Food & drink",
    "WMT": "Retail", "HD": "Retail", "MCD": "Restaurants",
    "MSFT": "Technology", "AAPL": "Technology",
    "JPM": "Banking", "NEE": "Utilities", "DUK": "Utilities",
    "XOM": "Energy", "VZ": "Telecoms",
}

COMPANY_NAMES = {
    "JNJ": "Johnson & Johnson", "UNH": "UnitedHealth", "ABBV": "AbbVie", "PG": "Procter & Gamble",
    "KO": "Coca-Cola", "PEP": "PepsiCo", "WMT": "Walmart", "HD": "Home Depot", "MCD": "McDonald's",
    "MSFT": "Microsoft", "AAPL": "Apple", "JPM": "JPMorgan Chase", "NEE": "NextEra Energy",
    "DUK": "Duke Energy", "XOM": "ExxonMobil", "VZ": "Verizon",
}

finnhubBaseUrl = "https://finnhub.io/api/v1"
secHeaders = {"User-Agent": os.getenv("SEC_USER_AGENT", "Heirloom hackathon project contact@example.com")}


# ---------------------------------------------------------------------------
# Yahoo Finance
# ---------------------------------------------------------------------------
def relativeStrengthIndex(prices: pd.Series, period=14) -> pd.Series:
    """RSI: 0–100. Above 70 often means a share has risen fast ("overbought"),
    below 30 that it has fallen fast ("oversold")."""
    priceChanges = prices.diff()
    averageGain = priceChanges.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    averageLoss = (-priceChanges.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - 100 / (1 + averageGain / averageLoss.replace(0, np.nan))


def computeIndicators(prices: pd.Series) -> dict:
    """Key price indicators from daily closing prices."""
    prices = prices.dropna()
    movingAverage50 = prices.rolling(50).mean().iloc[-1]
    movingAverage200 = prices.rolling(200).mean().iloc[-1]
    lastYear = prices.loc[prices.index >= prices.index[-1] - pd.Timedelta(days=365)]
    latestPrice = prices.iloc[-1]
    return {
        "movingAverage50": round(float(movingAverage50), 2),
        "movingAverage200": round(float(movingAverage200), 2),
        "distanceFrom200DayAverage": round(float(latestPrice / movingAverage200 - 1), 4),
        "rsi14": round(float(relativeStrengthIndex(prices).iloc[-1]), 1),
        "oneYearReturn": round(float(latestPrice / lastYear.iloc[0] - 1), 4),
        "distanceFrom52WeekHigh": round(float(latestPrice / lastYear.max() - 1), 4),
    }


def getYahooMetrics(tickers):
    """Returns (metrics per ticker, daily adjusted prices for charts and alerts)."""
    import yfinance as yf
    endDate = date.today()
    startDate = endDate - timedelta(days=5 * 365)
    downloaded = yf.download(list(tickers), start=startDate.isoformat(), end=endDate.isoformat(),
                             auto_adjust=False, actions=True, progress=False, group_by="ticker")
    metrics = {}
    adjustedPriceTable = {}
    for ticker in tickers:
        try:
            tickerData = downloaded[ticker].dropna(subset=["Adj Close"])
            adjustedPrices = tickerData["Adj Close"]
            adjustedPriceTable[ticker] = adjustedPrices
            yearsCovered = (adjustedPrices.index[-1] - adjustedPrices.index[0]).days / 365.25
            runningPeak = adjustedPrices.cummax()
            lastYearDividends = tickerData["Dividends"].loc[
                tickerData.index >= tickerData.index[-1] - pd.Timedelta(days=365)].sum()
            latestPrice = float(tickerData["Close"].iloc[-1])
            metrics[ticker] = {
                "latestPrice": round(latestPrice, 2),
                "fiveYearAnnualReturn": round((adjustedPrices.iloc[-1] / adjustedPrices.iloc[0]) ** (1 / yearsCovered) - 1, 4),
                "annualVolatility": round(float(adjustedPrices.pct_change().std() * np.sqrt(252)), 4),
                "worstFallFromPeak": round(float((adjustedPrices / runningPeak - 1).min()), 4),
                "dividendYield": round(float(lastYearDividends / latestPrice), 4),
                **computeIndicators(adjustedPrices),
            }
        except Exception as error:
            metrics[ticker] = {"error": f"Yahoo Finance: {error}"}
    return metrics, pd.DataFrame(adjustedPriceTable)


# ---------------------------------------------------------------------------
# Finnhub
# ---------------------------------------------------------------------------
def callFinnhub(path: str, params: dict):
    apiKey = os.getenv("FINNHUB_API_KEY")
    if not apiKey:
        return None
    response = requests.get(f"{finnhubBaseUrl}{path}", params={**params, "token": apiKey}, timeout=15)
    if response.status_code == 429:  # free plan: 60 calls a minute
        time.sleep(2)
        response = requests.get(f"{finnhubBaseUrl}{path}", params={**params, "token": apiKey}, timeout=15)
    response.raise_for_status()
    return response.json()


def getFinnhubData(ticker: str) -> dict:
    result = {}
    try:
        ratings = callFinnhub("/stock/recommendation", {"symbol": ticker})
        if ratings:
            latest = ratings[0]
            totalAnalysts = latest["strongBuy"] + latest["buy"] + latest["hold"] + latest["sell"] + latest["strongSell"]
            result["analystRatings"] = {
                "month": latest["period"],
                "buy": latest["strongBuy"] + latest["buy"], "hold": latest["hold"],
                "sell": latest["sell"] + latest["strongSell"],
                "buyShare": round((latest["strongBuy"] + latest["buy"]) / totalAnalysts, 2) if totalAnalysts else None,
            }

        metricData = callFinnhub("/stock/metric", {"symbol": ticker, "metric": "all"})
        if metricData:
            allMetrics = metricData.get("metric", {})
            result["valuation"] = {
                "priceToEarnings": allMetrics.get("peTTM"),
                "beta": allMetrics.get("beta"),
                "debtToEquity": allMetrics.get("totalDebt/totalEquityAnnual"),
            }

        today = date.today()
        news = callFinnhub("/company-news", {"symbol": ticker, "from": (today - timedelta(days=14)).isoformat(),
                                             "to": today.isoformat()})
        if news:
            result["recentHeadlines"] = [
                {"date": date.fromtimestamp(item["datetime"]).isoformat(), "headline": item["headline"],
                 "source": item.get("source", ""), "url": item.get("url", "")}
                for item in news[:5]
            ]
    except Exception as error:
        result["finnhubError"] = str(error)
    return result


# ---------------------------------------------------------------------------
# SEC EDGAR
# ---------------------------------------------------------------------------
REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
PROFIT_TAGS = ["NetIncomeLoss"]
DEBT_TAGS = ["LongTermDebtNoncurrent", "LongTermDebt"]


def getSecTickerMap() -> dict:
    cachePath = cacheFolder / "sec_company_tickers.json"
    if cachePath.exists():
        return json.loads(cachePath.read_text())
    response = requests.get("https://www.sec.gov/files/company_tickers.json", headers=secHeaders, timeout=20)
    response.raise_for_status()
    tickerMap = {entry["ticker"]: str(entry["cik_str"]).zfill(10) for entry in response.json().values()}
    cachePath.write_text(json.dumps(tickerMap))
    return tickerMap


def latestAnnualValues(usGaapFacts: dict, possibleTags: list, yearsWanted=3) -> list:
    """Most recent yearly (10-K) values for the first tag the company reports."""
    for tag in possibleTags:
        if tag not in usGaapFacts:
            continue
        entries = usGaapFacts[tag]["units"].get("USD", [])
        yearlyEntries = {}
        for entry in entries:
            # SEC "frames" label each value's calendar period: CY2023 is a full year
            # (income), CY2023Q4I is the year-end balance (debt).
            frameMatch = re.fullmatch(r"CY(\d{4})(Q4I)?", entry.get("frame", ""))
            if entry.get("form", "").startswith("10-K") and frameMatch:
                yearlyEntries[int(frameMatch.group(1))] = entry["val"]
        if yearlyEntries:
            return [{"year": year, "value": yearlyEntries[year]}
                    for year in sorted(yearlyEntries)[-yearsWanted:]]
    return []


def getSecFinancials(ticker: str) -> dict:
    try:
        centralIndexKey = getSecTickerMap().get(ticker)
        if not centralIndexKey:
            return {}
        response = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{centralIndexKey}.json",
                                headers=secHeaders, timeout=20)
        response.raise_for_status()
        usGaapFacts = response.json()["facts"].get("us-gaap", {})
        revenue = latestAnnualValues(usGaapFacts, REVENUE_TAGS)
        profit = latestAnnualValues(usGaapFacts, PROFIT_TAGS)
        debt = latestAnnualValues(usGaapFacts, DEBT_TAGS, yearsWanted=1)
        financials = {"revenueByYear": revenue, "profitByYear": profit}
        if len(revenue) >= 2 and revenue[0]["value"]:
            financials["revenueGrowthPerYear"] = round(
                (revenue[-1]["value"] / revenue[0]["value"]) ** (1 / (len(revenue) - 1)) - 1, 4)
        if revenue and profit and revenue[-1]["value"]:
            financials["profitMargin"] = round(profit[-1]["value"] / revenue[-1]["value"], 4)
        if debt:
            financials["longTermDebt"] = debt[-1]["value"]
        time.sleep(0.15)  # SEC asks for no more than 10 requests a second
        return financials
    except Exception as error:
        return {"secError": str(error)}


# ---------------------------------------------------------------------------
# Snapshot: everything together, cached for the day
# ---------------------------------------------------------------------------
def buildSnapshot(tickers=None, useCache=True) -> dict:
    """All the data for the AI: stocks (full detail) and our funds (prices + indicators)."""
    from planner import FUND_LIBRARY
    tickers = list(tickers or CANDIDATE_STOCKS)
    cachePath = cacheFolder / f"stock_snapshot_{date.today().isoformat()}.json"
    if useCache and cachePath.exists():
        cached = json.loads(cachePath.read_text())
        if set(tickers) <= set(cached["stocks"]):
            return cached

    try:
        yahooMetrics, adjustedPrices = getYahooMetrics(tickers + list(FUND_LIBRARY))
    except Exception as error:
        # Offline: use the newest snapshot we have.
        olderSnapshots = sorted(cacheFolder.glob("stock_snapshot_*.json"))
        if olderSnapshots:
            return json.loads(olderSnapshots[-1].read_text())
        raise RuntimeError(f"No market data available: {error}")

    stocks = {}
    for ticker in tickers:
        stocks[ticker] = {
            "industry": CANDIDATE_STOCKS.get(ticker, "Unknown"),
            "yahooFinance": yahooMetrics.get(ticker, {}),
            "finnhub": getFinnhubData(ticker),
            "secFilings": getSecFinancials(ticker),
        }
    funds = {ticker: yahooMetrics.get(ticker, {}) for ticker in FUND_LIBRARY}
    snapshot = {"builtOn": date.today().isoformat(), "economy": getCurrentRates(),
                "stocks": stocks, "funds": funds}
    cachePath.write_text(json.dumps(snapshot, indent=1, default=str))
    # Keep 3 years of daily prices for the charts and buy/sell alerts.
    recentPrices = adjustedPrices.loc[adjustedPrices.index >= adjustedPrices.index[-1] - pd.Timedelta(days=3 * 365)]
    recentPrices.round(3).to_csv(cacheFolder / f"prices_{date.today().isoformat()}.csv")
    return snapshot


def loadPriceHistory() -> pd.DataFrame:
    """Newest saved daily prices (one column per ticker)."""
    priceFiles = sorted(cacheFolder.glob("prices_*.csv"))
    if not priceFiles:
        return pd.DataFrame()
    return pd.read_csv(priceFiles[-1], index_col=0, parse_dates=True)


def latestPriceFor(snapshot: dict, ticker: str):
    source = snapshot["stocks"].get(ticker, {}).get("yahooFinance") or snapshot.get("funds", {}).get(ticker, {})
    return source.get("latestPrice")


if __name__ == "__main__":
    builtSnapshot = buildSnapshot(useCache=False)
    print("Funds:", ", ".join(builtSnapshot["funds"]))
    for tickerName, stockData in builtSnapshot["stocks"].items():
        yahooPart = stockData["yahooFinance"]
        print(f"{tickerName:5} {stockData['industry']:16} "
              f"growth {yahooPart.get('fiveYearAnnualReturn', 'n/a')}  "
              f"worst fall {yahooPart.get('worstFallFromPeak', 'n/a')}  "
              f"analyst buy share {stockData['finnhub'].get('analystRatings', {}).get('buyShare', 'n/a')}")
    print("Saved snapshot to data/cache/")
