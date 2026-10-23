"""
signals.py — buy / sell / rebalance alerts.

Nobody can reliably time the market, so these are "price signals", not promises.
They use three well-known indicators, explained in plain English to the client:

  - 200-day average: the share's usual price over the last ~10 months
  - RSI (0–100): how fast the price has moved lately; under 35 = fallen fast,
    over 70 = risen fast
  - Drift: how far a pot has moved away from the plan (rebalancing is the
    safest, best-evidenced "buy low, sell high" habit for retirees)
"""

from datetime import date

import pandas as pd

from stock_data import COMPANY_NAMES, relativeStrengthIndex

BUY_RULE = {"maxDistanceFromAverage": -0.05, "maxRsi": 35}
SELL_RULE = {"minDistanceFromAverage": 0.15, "minRsi": 72}
FALLING_RULE = {"maxDistanceFromAverage": -0.15}
REBALANCE_DRIFT = 0.05   # alert when a holding is 5 percentage points off plan


def signalFromIndicators(indicators: dict):
    """Today's signal for one share or fund, or None if nothing stands out."""
    distance = indicators.get("distanceFrom200DayAverage")
    rsi = indicators.get("rsi14")
    if distance is None or rsi is None:
        return None
    if distance <= BUY_RULE["maxDistanceFromAverage"] and rsi <= BUY_RULE["maxRsi"]:
        return {"action": "buy", "title": "Good moment to add",
                "facts": f"price is {abs(distance):.0%} below its usual level and has fallen quickly (RSI {rsi:.0f})"}
    if distance >= SELL_RULE["minDistanceFromAverage"] and rsi >= SELL_RULE["minRsi"]:
        return {"action": "sell", "title": "Consider taking some profit",
                "facts": f"price is {distance:.0%} above its usual level and has risen quickly (RSI {rsi:.0f})"}
    if distance <= FALLING_RULE["maxDistanceFromAverage"]:
        return {"action": "wait", "title": "Falling trend: wait before adding more",
                "facts": f"price is {abs(distance):.0%} below its usual level and still sliding"}
    return None


def historicalSignals(prices: pd.Series) -> pd.DataFrame:
    """Days in the past when the rules above fired (first day of each run),
    for the buy/sell markers on the price chart."""
    prices = prices.dropna()
    movingAverage200 = prices.rolling(200).mean()
    distance = prices / movingAverage200 - 1
    rsi = relativeStrengthIndex(prices)
    buyDays = (distance <= BUY_RULE["maxDistanceFromAverage"]) & (rsi <= BUY_RULE["maxRsi"])
    sellDays = (distance >= SELL_RULE["minDistanceFromAverage"]) & (rsi >= SELL_RULE["minRsi"])
    markerRows = []
    for action, flaggedDays in (("buy", buyDays), ("sell", sellDays)):
        firstDays = flaggedDays & ~flaggedDays.shift(1, fill_value=False)
        for day in prices.index[firstDays.reindex(prices.index, fill_value=False)]:
            markerRows.append({"Date": day, "Price": prices.loc[day], "Signal": action})
    return pd.DataFrame(markerRows, columns=["Date", "Price", "Signal"])


def holdingCurrentValues(holdings: list, snapshot: dict, purchases=None) -> list:
    """Value each holding today.

    purchases=None: value the whole plan as if bought on the plan day (used for alerts).
    purchases={holdingKey: {"date", "price"}}: only holdings the person has actually
    bought grow, from the price on the day they bought; the rest is cash waiting to invest."""
    from portfolio import holdingKeyFor
    from stock_data import latestPriceFor
    valuedHoldings = []
    for holding in holdings:
        latestPrice = latestPriceFor(snapshot, holding["ticker"])
        if purchases is None:
            startPrice, isInvested = holding.get("priceAtPlan"), True
        else:
            purchase = purchases.get(holdingKeyFor(holding))
            isInvested = purchase is not None
            startPrice = purchase.get("price") if purchase else None
        growth = latestPrice / startPrice if isInvested and latestPrice and startPrice else 1.0
        valuedHoldings.append({**holding, "currentValue": holding["amount"] * growth, "isInvested": isInvested})
    return valuedHoldings


def buildAlerts(profile: dict, snapshot: dict, brokerLink) -> list:
    """All alerts for one client: price signals on what they own, buying
    chances on shares that suit them, and rebalancing."""
    alerts = []
    today = date.today().isoformat()
    # The same fund can appear for retirement and for legacy; judge it once.
    holdingsByTicker = {}
    for holding in holdingCurrentValues(profile["holdings"], snapshot):
        combined = holdingsByTicker.setdefault(holding["ticker"], {**holding, "amount": 0, "currentValue": 0})
        combined["amount"] += holding["amount"]
        combined["currentValue"] += holding["currentValue"]
    holdings = list(holdingsByTicker.values())
    totalNow = sum(holding["currentValue"] for holding in holdings) or 1
    totalPlanned = sum(holding["amount"] for holding in holdings) or 1

    for holding in holdings:
        ticker = holding["ticker"]
        indicators = (snapshot["stocks"].get(ticker, {}).get("yahooFinance")
                      or snapshot.get("funds", {}).get(ticker, {}))
        signal = signalFromIndicators(indicators)

        targetShare = holding["amount"] / totalPlanned
        currentShare = holding["currentValue"] / totalNow
        drift = currentShare - targetShare

        if signal and signal["action"] == "sell" and drift > 0:
            sellAmount = round(drift * totalNow / 100) * 100
            if sellAmount >= 100:
                alerts.append({"type": "sell", "ticker": ticker, "date": today, "title": signal["title"],
                               "message": f"{holding['name']}: {signal['facts']}. Selling about "
                                          f"${sellAmount:,.0f} would lock in gains and bring it back to your plan.",
                               "amount": sellAmount, "link": brokerLink(ticker)})
                continue
        if signal and signal["action"] in ("buy", "wait"):
            alerts.append({"type": signal["action"], "ticker": ticker, "date": today, "title": signal["title"],
                           "message": f"{holding['name']}: {signal['facts']}."
                                      + (" If you're adding money, this looks like a good moment."
                                         if signal["action"] == "buy" else " No need to sell. Your plan expects ups and downs."),
                           "amount": None, "link": brokerLink(ticker) if signal["action"] == "buy" else None})
        if abs(drift) >= REBALANCE_DRIFT:
            action = "sell" if drift > 0 else "buy"
            alerts.append({"type": "rebalance", "ticker": ticker, "date": today,
                           "title": f"Time to rebalance: {action} some {ticker}",
                           "message": f"{holding['name']} is now {currentShare:.0%} of your savings instead of {targetShare:.0%}. "
                                      f"To get back on plan, {action} about ${abs(drift) * totalNow:,.0f}.",
                           "amount": round(abs(drift) * totalNow / 100) * 100, "link": brokerLink(ticker)})

    # Buying chances on suitable shares the client doesn't own yet.
    ownedTickers = {holding["ticker"] for holding in holdings}
    avoided = set(profile["answers"].get("avoidIndustries", []))
    for ticker, stockData in snapshot["stocks"].items():
        if ticker in ownedTickers or stockData["industry"] in avoided:
            continue
        signal = signalFromIndicators(stockData.get("yahooFinance", {}))
        if signal and signal["action"] == "buy":
            alerts.append({"type": "watch", "ticker": ticker, "date": today,
                           "title": f"On sale: {COMPANY_NAMES.get(ticker, ticker)} ({stockData['industry']})",
                           "message": f"{signal['facts']}. Worth a look if you're adding money.",
                           "amount": None, "link": brokerLink(ticker)})
    return alerts
