"""
history.py — what has happened so far.

- logEvent:     adds a line to the activity timeline (plan made, investment done, alert sent...)
- recordValue:  saves today's total value once a day, for the "your money over time" chart
- backtestPlan: how this exact plan would have done over the past year, using real prices
"""

from datetime import date

import pandas as pd

from users import saveProfile


def logEvent(profile: dict, icon: str, text: str, detail: str = "", save=True):
    profile.setdefault("history", []).insert(0, {"date": date.today().isoformat(), "icon": icon,
                                                  "text": text, "detail": detail})
    profile["history"] = profile["history"][:200]
    if save:
        saveProfile(profile)


def recordValue(profile: dict, value: float):
    """One point per day; today's point is updated if it already exists."""
    today = date.today().isoformat()
    valueHistory = profile.setdefault("valueHistory", [])
    if valueHistory and valueHistory[-1]["date"] == today:
        if abs(valueHistory[-1]["value"] - value) < 0.01:
            return
        valueHistory[-1]["value"] = round(value, 2)
    else:
        valueHistory.append({"date": today, "value": round(value, 2)})
    saveProfile(profile)


def backtestPlan(holdings: list, priceHistory: pd.DataFrame, days=365) -> pd.DataFrame:
    """Value per day if the plan had been bought `days` ago. Holdings without
    price history are counted at their planned amount (no growth)."""
    if priceHistory.empty:
        return pd.DataFrame()
    recentPrices = priceHistory.loc[priceHistory.index >= priceHistory.index[-1] - pd.Timedelta(days=days)].ffill()
    dailyValue = pd.Series(0.0, index=recentPrices.index)
    for holding in holdings:
        ticker = holding["ticker"]
        if ticker in recentPrices and recentPrices[ticker].notna().any():
            prices = recentPrices[ticker].bfill()
            dailyValue += holding["amount"] * prices / prices.iloc[0]
        else:
            dailyValue += holding["amount"]
    return pd.DataFrame({"Date": dailyValue.index, "Value": dailyValue.values})
