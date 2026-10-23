"""
stock_advisor.py — the AI stock picker.

How it works:
  1. stock_data.buildSnapshot() gathers public data for each candidate stock
  2. scoreStocks() gives each one a "steadiness score" from the numbers, so the
     AI starts from something objective and the judges can check it
  3. GPT-6.1 Sol reads the numbers, analyst ratings, filings AND news headlines,
     then picks stocks, sets dollar amounts and explains why (as JSON)
  4. applySafetyLimits() checks the AI's answer: only known stocks, no more
     than a set share per company or per industry, amounts add up exactly

Try it from the terminal:  python stock_advisor.py
"""

import json
import os

import numpy as np
from dotenv import load_dotenv

from stock_data import CANDIDATE_STOCKS, buildSnapshot

load_dotenv()

modelName = os.getenv("MODEL_NAME", "gpt-6.1-sol")

# How spread out the stock slice must be, by the client's comfort with risk.
SAFETY_LIMITS = {
    "low":  {"numberOfStocks": 8, "maxPerStock": 0.15, "maxPerIndustry": 0.30},
    "mid":  {"numberOfStocks": 7, "maxPerStock": 0.18, "maxPerIndustry": 0.35},
    "high": {"numberOfStocks": 6, "maxPerStock": 0.20, "maxPerIndustry": 0.40},
}

# What matters for a steady retirement portfolio, and how much.
SCORE_WEIGHTS = {
    "annualVolatility": (-1, 0.20),       # lower is better
    "worstFallFromPeak": (+1, 0.15),      # less negative is better
    "dividendYield": (+1, 0.15),
    "fiveYearAnnualReturn": (+1, 0.15),
    "analystBuyShare": (+1, 0.15),
    "profitMargin": (+1, 0.10),
    "priceToEarnings": (-1, 0.05),        # cheaper is better
    "debtToEquity": (-1, 0.05),           # less debt is better
}

# Clients who want regular income care more about dividends, less about growth.
INCOME_SCORE_WEIGHTS = {**SCORE_WEIGHTS, "dividendYield": (+1, 0.30), "fiveYearAnnualReturn": (+1, 0.05),
                        "annualVolatility": (-1, 0.15)}
GROWTH_SCORE_WEIGHTS = {**SCORE_WEIGHTS, "dividendYield": (+1, 0.05), "fiveYearAnnualReturn": (+1, 0.25)}

# Plain names for the key indicators, used on screen and in the AI prompt.
INDICATOR_LABELS = {
    "annualVolatility": "Ups and downs per year",
    "worstFallFromPeak": "Worst fall in 5 years",
    "dividendYield": "Dividend paid per year",
    "fiveYearAnnualReturn": "Growth per year (5 yrs)",
    "analystBuyShare": "Analysts saying buy",
    "profitMargin": "Profit margin",
    "priceToEarnings": "Price vs earnings (P/E)",
    "debtToEquity": "Debt vs company value",
}


# ---------------------------------------------------------------------------
# 1. Objective score
# ---------------------------------------------------------------------------
def flattenStock(stockData: dict) -> dict:
    yahooPart = stockData.get("yahooFinance", {})
    return {
        "annualVolatility": yahooPart.get("annualVolatility"),
        "worstFallFromPeak": yahooPart.get("worstFallFromPeak"),
        "dividendYield": yahooPart.get("dividendYield"),
        "fiveYearAnnualReturn": yahooPart.get("fiveYearAnnualReturn"),
        "analystBuyShare": stockData.get("finnhub", {}).get("analystRatings", {}).get("buyShare"),
        "profitMargin": stockData.get("secFilings", {}).get("profitMargin"),
        "priceToEarnings": positiveOrNone(stockData.get("finnhub", {}).get("valuation", {}).get("priceToEarnings")),
        "debtToEquity": stockData.get("finnhub", {}).get("valuation", {}).get("debtToEquity"),
    }


def positiveOrNone(value):
    return value if isinstance(value, (int, float)) and value > 0 else None


def scoreStocks(snapshot: dict, scoreWeights=None) -> dict:
    """0–100 steadiness score. Each measure is ranked against the other
    candidates; missing data counts as average rather than good or bad."""
    flatStocks = {ticker: flattenStock(data) for ticker, data in snapshot["stocks"].items()}
    tickers = list(flatStocks)
    scores = {ticker: 0.0 for ticker in tickers}
    for measure, (direction, weight) in (scoreWeights or SCORE_WEIGHTS).items():
        values = np.array([flatStocks[ticker][measure] if flatStocks[ticker][measure] is not None
                           else np.nan for ticker in tickers], dtype=float)
        knownValues = values[~np.isnan(values)]
        for i, ticker in enumerate(tickers):
            if np.isnan(values[i]) or len(knownValues) < 2:
                rankShare = 0.5
            else:
                rankShare = (knownValues < values[i]).mean() if direction > 0 else (knownValues > values[i]).mean()
            scores[ticker] += weight * rankShare
    return {ticker: round(score * 100) for ticker, score in scores.items()}


# ---------------------------------------------------------------------------
# 2. Ask the AI
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the stock analyst inside Heirloom, an educational tool for
retirees. You pick a small, steady set of shares for the long-term "Family Tree" pot.

Rules:
- Only pick tickers from the data given. Never invent figures.
- Analyse the key indicators together: steadiness (volatility, worst fall), income
  (dividend yield), quality (profit margin, revenue growth, debt to equity), value
  (P/E), analyst views, and price trend (distance from 200-day average, RSI).
- Favour steadiness. High growth alone is not enough. A share far above its 200-day
  average with RSI over 70 may be expensive right now: give it less.
- Respect the client's preferences exactly (avoided industries, income vs growth).
- Read the news headlines. If a headline suggests a serious problem (lawsuit, fraud,
  big profit warning), say so and lower or skip that stock.
- Each reason: one or two plain-English sentences a 72-year-old understands, quoting at
  least one number and its source (Yahoo Finance, Finnhub, SEC filings, FRED).
- Reply with JSON only."""

RESPONSE_SHAPE = """{
  "summary": "2 sentences on the overall approach",
  "picks": [{"ticker": "KO", "amount": 4000, "reason": "...", "newsNote": "... or empty",
             "confidence": "high | medium | low"}],
  "skipped": [{"ticker": "XOM", "reason": "..."}],
  "risks": ["plain-English risk 1", "risk 2"]
}"""


def compactSnapshot(snapshot: dict, scores: dict) -> dict:
    compact = {}
    for ticker, stockData in snapshot["stocks"].items():
        secPart = {key: value for key, value in stockData.get("secFilings", {}).items()
                   if key in ("revenueGrowthPerYear", "profitMargin", "longTermDebt")}
        compact[ticker] = {
            "industry": stockData.get("industry"),
            "steadinessScore": scores[ticker],
            "yahooFinance": stockData.get("yahooFinance"),
            "finnhubAnalysts": stockData.get("finnhub", {}).get("analystRatings"),
            "finnhubValuation": stockData.get("finnhub", {}).get("valuation"),
            "newsHeadlines": [item["headline"] for item in stockData.get("finnhub", {}).get("recentHeadlines", [])],
            "secFilings": secPart,
        }
    return compact


def askModelForPicks(snapshot, scores, clientProfile, amount, limits):
    apiKey = os.getenv("OPENAI_API_KEY")
    if not apiKey:
        return None, "No OPENAI_API_KEY set"
    from openai import OpenAI
    client = OpenAI(api_key=apiKey, base_url=os.getenv("OPENAI_BASE_URL") or None, timeout=90)

    userMessage = (
        f"CLIENT: {clientProfile}\n"
        f"AMOUNT TO INVEST IN SHARES: ${amount:,.0f}\n"
        f"LIMITS: pick about {limits['numberOfStocks']} stocks; no stock above "
        f"{limits['maxPerStock']:.0%} of the amount; no industry above {limits['maxPerIndustry']:.0%}. "
        f"Amounts must add up to exactly ${amount:,.0f} and be multiples of $100.\n"
        f"ECONOMY (FRED): {json.dumps(snapshot.get('economy'))}\n\n"
        f"STOCK DATA:\n{json.dumps(compactSnapshot(snapshot, scores), default=str)}\n\n"
        f"Reply in exactly this JSON shape:\n{RESPONSE_SHAPE}"
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": userMessage}]
    try:
        try:
            response = client.chat.completions.create(model=modelName, messages=messages,
                                                      response_format={"type": "json_object"})
        except Exception:
            # Some portals don't support JSON mode; ask without it.
            response = client.chat.completions.create(model=modelName, messages=messages)
        replyText = response.choices[0].message.content
        return json.loads(replyText[replyText.find("{"): replyText.rfind("}") + 1]), None
    except Exception as error:
        return None, f"AI request failed: {error}"


# ---------------------------------------------------------------------------
# 3. Check the AI's answer
# ---------------------------------------------------------------------------
def applySafetyLimits(rawAmounts: dict, amount: float, limits: dict, allowedTickers=None):
    """Keep only known stocks, cap each stock and industry, make amounts add up.
    Anything that can't fit within the limits goes into a world index fund (VT)."""
    adjustments = []
    weights = {}
    for ticker, value in rawAmounts.items():
        if ticker not in CANDIDATE_STOCKS:
            adjustments.append(f"Removed {ticker}: not on our checked list of stocks.")
        elif allowedTickers is not None and ticker not in allowedTickers:
            adjustments.append(f"Removed {ticker}: its industry is on your 'avoid' list.")
        elif value and value > 0:
            weights[ticker] = float(value)
    if not weights:
        return {"VT": amount}, adjustments + ["No valid picks, so everything goes into the world fund."]

    totalWeight = sum(weights.values())
    weights = {ticker: value / totalWeight for ticker, value in weights.items()}
    maxPerStock, maxPerIndustry = limits["maxPerStock"], limits["maxPerIndustry"]

    # Step 1: trim anything over a limit.
    for ticker in weights:
        if weights[ticker] > maxPerStock:
            adjustments.append(f"Lowered {ticker} to the {maxPerStock:.0%} limit per company.")
            weights[ticker] = maxPerStock
    for industry in set(CANDIDATE_STOCKS[ticker] for ticker in weights):
        industryTickers = [ticker for ticker in weights if CANDIDATE_STOCKS[ticker] == industry]
        industryTotal = sum(weights[ticker] for ticker in industryTickers)
        if industryTotal > maxPerIndustry:
            adjustments.append(f"Lowered {industry} to the {maxPerIndustry:.0%} limit per industry.")
            for ticker in industryTickers:
                weights[ticker] *= maxPerIndustry / industryTotal

    # Step 2: hand the trimmed money back to picks that still have room,
    # biggest picks first, never breaking either limit.
    for _ in range(10):
        leftOver = 1 - sum(weights.values())
        if leftOver < 1e-6:
            break
        industryUsed = {}
        for ticker, weight in weights.items():
            industryUsed[CANDIDATE_STOCKS[ticker]] = industryUsed.get(CANDIDATE_STOCKS[ticker], 0) + weight
        currentTotal = sum(weights.values())
        gaveSomething = False
        for ticker in sorted(weights, key=weights.get, reverse=True):
            industry = CANDIDATE_STOCKS[ticker]
            fairShare = leftOver * weights[ticker] / currentTotal
            room = min(maxPerStock - weights[ticker], maxPerIndustry - industryUsed[industry])
            extra = max(0.0, min(fairShare, room))
            if extra > 1e-9:
                weights[ticker] += extra
                industryUsed[industry] += extra
                gaveSomething = True
        if not gaveSomething:
            break

    amounts = {ticker: round(amount * weight / 100) * 100 for ticker, weight in weights.items()}
    amounts = {ticker: value for ticker, value in amounts.items() if value > 0}
    remainder = amount - sum(amounts.values())
    if remainder >= 1000:
        amounts["VT"] = remainder
        adjustments.append(f"${remainder:,.0f} didn't fit within the safety limits, so it goes into a "
                           "world index fund (VT) for extra spreading out.")
    elif remainder and amounts:
        amounts[max(amounts, key=amounts.get)] += remainder
    return amounts, list(dict.fromkeys(adjustments))


# ---------------------------------------------------------------------------
# 4. Put it together
# ---------------------------------------------------------------------------
def templateReason(stockData: dict) -> str:
    flat = flattenStock(stockData)
    sentences = []
    yahooParts = []
    if flat["worstFallFromPeak"] is not None:
        yahooParts.append(f"its worst fall in 5 years was {abs(flat['worstFallFromPeak']):.0%}")
    if flat["dividendYield"]:
        yahooParts.append(f"it pays about {flat['dividendYield']:.1%} a year in dividends")
    if yahooParts:
        sentences.append(" and ".join(yahooParts).capitalize() + " (Yahoo Finance).")
    if flat["analystBuyShare"] is not None:
        sentences.append(f"{flat['analystBuyShare']:.0%} of analysts rate it a buy (Finnhub).")
    if flat["profitMargin"] is not None:
        sentences.append(f"It keeps {flat['profitMargin']:.0%} of its sales as profit (SEC filings).")
    return " ".join(sentences) or "Chosen for its steadiness score."


def recommendStocks(amount=30_000, riskLevel="low", clientProfile=None, snapshot=None,
                    avoidIndustries=(), incomePreference="balanced") -> dict:
    """incomePreference: 'income' (dividends), 'growth' or 'balanced'.
    avoidIndustries: industries the client doesn't want to own, e.g. ['Energy']."""
    limits = SAFETY_LIMITS[riskLevel]
    fullSnapshot = snapshot or buildSnapshot()
    allowedStocks = {ticker: data for ticker, data in fullSnapshot["stocks"].items()
                     if data["industry"] not in avoidIndustries}
    snapshot = {**fullSnapshot, "stocks": allowedStocks}
    scoreWeights = {"income": INCOME_SCORE_WEIGHTS, "growth": GROWTH_SCORE_WEIGHTS}.get(incomePreference)
    scores = scoreStocks(snapshot, scoreWeights)
    clientProfile = clientProfile or "A beginner investor with $100,000 who wants steady long-term growth."
    clientProfile += (f" Preference: {incomePreference}."
                      + (f" Do NOT pick these industries: {', '.join(avoidIndustries)}." if avoidIndustries else ""))

    aiAnswer, aiProblem = askModelForPicks(snapshot, scores, clientProfile, amount, limits)
    if aiAnswer and aiAnswer.get("picks"):
        source = f"AI analysis ({modelName})"
        rawAmounts = {pick["ticker"].upper(): pick.get("amount", 0) for pick in aiAnswer["picks"]}
        aiDetails = {pick["ticker"].upper(): pick for pick in aiAnswer["picks"]}
    else:
        # Fallback: highest steadiness scores, weighted by score.
        source = "Steadiness score only (AI not connected)"
        topTickers = sorted(scores, key=scores.get, reverse=True)[:limits["numberOfStocks"]]
        rawAmounts = {ticker: scores[ticker] for ticker in topTickers}
        aiDetails = {}
        aiAnswer = {"summary": "These are the steadiest companies on our list by the numbers alone.",
                    "skipped": [], "risks": ["Individual company shares can fall sharply, even steady ones."]}

    finalAmounts, adjustments = applySafetyLimits(rawAmounts, amount, limits, allowedTickers=set(allowedStocks))
    picks = []
    for ticker, pickAmount in sorted(finalAmounts.items(), key=lambda item: -item[1]):
        details = aiDetails.get(ticker, {})
        if ticker == "VT":
            picks.append({"ticker": "VT", "industry": "World index fund", "amount": pickAmount,
                          "share": pickAmount / amount, "steadinessScore": None,
                          "reason": "Thousands of companies worldwide in one fund, so no single company can hurt the plan much.",
                          "newsNote": "", "confidence": "high", "latestPrice": None, "headlines": []})
            continue
        stockData = snapshot["stocks"][ticker]
        picks.append({
            "ticker": ticker, "industry": stockData["industry"], "amount": pickAmount,
            "share": pickAmount / amount, "steadinessScore": scores[ticker],
            "reason": details.get("reason") or templateReason(stockData),
            "newsNote": details.get("newsNote", ""),
            "confidence": details.get("confidence", "medium"),
            "latestPrice": stockData["yahooFinance"].get("latestPrice"),
            "headlines": stockData.get("finnhub", {}).get("recentHeadlines", []),
        })
    return {
        "source": source, "aiProblem": aiProblem, "summary": aiAnswer.get("summary", ""),
        "picks": picks, "skipped": aiAnswer.get("skipped", []), "risks": aiAnswer.get("risks", []),
        "adjustments": adjustments, "scores": scores, "dataDate": snapshot.get("builtOn"),
    }


if __name__ == "__main__":
    result = recommendStocks()
    print(f"\n{result['source']}  ·  data from {result['dataDate']}")
    if result["aiProblem"]:
        print("Note:", result["aiProblem"])
    print(result["summary"], "\n")
    for pick in result["picks"]:
        print(f"  {pick['ticker']:5} ${pick['amount']:>7,.0f}  ({pick['share']:.0%})  score {pick['steadinessScore']}")
        print(f"        {pick['reason']}")
    for adjustment in result["adjustments"]:
        print("  Safety check:", adjustment)
