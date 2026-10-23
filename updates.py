"""
updates.py — the home page feed: what to invest in, when, and how much.

Order: smart-timing alerts first, then the investments still to make (each with
a "when" based on its price signal), then the goal check and the rebalancing reminder.
"""

from portfolio import POT_SAFETY, brokerLink, holdingKeyFor
from signals import signalFromIndicators

WHEN_STYLES = {
    "Now": ("🟢", "#2E9E4F"),
    "Good moment": ("🟢", "#2E9E4F"),
    "In two halves": ("🟡", "#C9A227"),
    "Wait": ("🟡", "#C9A227"),
    "Take profit": ("🟠", "#E08E2B"),
    "Rebalance": ("⚖️", "#3B6EA5"),
    "Goal": ("🎯", "#3B6EA5"),
    "Every 6 months": ("🗓️", "#666666"),
    "Done": ("✅", "#888888"),
}


def indicatorsFor(ticker: str, snapshot: dict) -> dict:
    return (snapshot["stocks"].get(ticker, {}).get("yahooFinance")
            or snapshot.get("funds", {}).get(ticker, {}))


def timingFor(holding: dict, snapshot: dict):
    """When to buy this holding, from its price signal. Safe funds: always now."""
    if holding["pot"] == POT_SAFETY:
        return "Now", "Safe funds barely move in price, so there's no need to wait."
    signal = signalFromIndicators(indicatorsFor(holding["ticker"], snapshot))
    if signal is None:
        return "Now", "The price is close to its usual level, so now is a reasonable time."
    if signal["action"] == "buy":
        return "Good moment", f"Its {signal['facts']}, so it's cheaper than usual."
    if signal["action"] == "wait":
        return "Wait", f"Its {signal['facts']}. We'll email you when it settles."
    return "In two halves", (f"Its {signal['facts']}. Buy half now and half in about a month "
                             "so you don't pay the top price for all of it.")


def buildUpdates(profile: dict, snapshot: dict, alerts: list) -> list:
    updates = []
    boughtKeys = set(profile.get("boughtTickers", []))

    # 1. Smart-timing alerts on things they already own
    for alert in alerts:
        if alert["type"] in ("sell", "rebalance"):
            updates.append({"when": "Take profit" if alert["type"] == "sell" else "Rebalance",
                            "title": alert["title"], "message": alert["message"], "ticker": alert["ticker"],
                            "amount": alert.get("amount"), "link": alert["link"], "buttonWord": "Sell"
                            if alert["type"] == "sell" or "sell" in alert["title"].lower() else "Invest"})

    # 2. What to invest in, how much, and when
    for holding in profile["holdings"]:
        holdingKey = holdingKeyFor(holding)
        if holdingKey in boughtKeys:
            continue
        when, timingText = timingFor(holding, snapshot)
        amountNow = holding["amount"] / 2 if when == "In two halves" else holding["amount"]
        updates.append({"when": when, "title": f"Invest ${amountNow:,.0f} in {holding['name']} ({holding['ticker']})",
                        "message": timingText, "ticker": holding["ticker"], "amount": amountNow,
                        "link": brokerLink(holding["ticker"]), "buttonWord": "Invest",
                        "holding": holding, "holdingKey": holdingKey})

    # Best timing first: good moments, then now, then the ones to stagger or wait on
    timingOrder = {"Take profit": 0, "Rebalance": 1, "Good moment": 2, "Now": 3, "In two halves": 4, "Wait": 5}
    updates.sort(key=lambda update: timingOrder.get(update["when"], 9))

    # 3. Buying chances on suitable shares they don't own
    for alert in alerts:
        if alert["type"] == "watch":
            updates.append({"when": "Good moment", "title": alert["title"], "message": alert["message"][0].upper() + alert["message"][1:],
                            "ticker": alert["ticker"], "amount": None, "link": alert["link"], "buttonWord": "View"})

    # 4. Goal check and the regular habit that keeps the plan on track
    projection = profile["projection"]
    answers = profile["answers"]
    chance = projection["chanceOfReachingGoal"]
    if chance >= 0.6:
        goalText = (f"You're on track. In {chance:.0%} of our simulated futures you reach "
                    f"${answers['goalAmount']:,.0f} within {answers['goalYears']} years.")
    else:
        goalText = (f"Your goal is a stretch: {chance:.0%} chance of reaching ${answers['goalAmount']:,.0f} "
                    f"in {answers['goalYears']} years. You'd need about {projection['requiredReturn']:.1%} a year; "
                    f"this plan typically makes about {projection['expectedReturn']:.1%}. Giving it more time "
                    "helps more than taking more risk.")
    updates.append({"when": "Goal", "title": "Progress towards your goal", "message": goalText,
                    "ticker": None, "amount": None, "link": None})
    updates.append({"when": "Every 6 months", "title": "Check your balance",
                    "message": "Twice a year, move money back to your planned amounts. It's a simple way to "
                               "sell what's grown and buy what's cheap. We'll remind you.",
                    "ticker": None, "amount": None, "link": None})
    return updates
