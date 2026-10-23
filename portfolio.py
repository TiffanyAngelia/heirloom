"""
portfolio.py — turns sign-up answers into a goal-based plan for the money.

The money can be for two purposes, and every investment is labelled with one:
  🏖️ Retirement  money you'll live on: more safety, more steady income
  🎁 Legacy      money you'll leave to family: longer time, more growth

Each purpose is built from three parts:
  🛡️ Safety cushion   short-term government bonds and cash-like funds
  🌍 Core funds        world shares and bonds (thousands of companies at once)
  🤖 AI share picks    steady companies chosen by GPT-6.1 Sol from public data
                       (in the legacy money if there is any, because it has the most time)
"""

import os
from dataclasses import asdict, dataclass, field
from datetime import date
from urllib.parse import quote

from planner import FUND_LIBRARY, TREE_BUNDLES, UMBRELLA_BUNDLES, Plan
from simulator import simulateFuture
from stock_advisor import recommendStocks
from stock_data import COMPANY_NAMES, latestPriceFor

POT_SAFETY = "Safety cushion"
POT_CORE = "Core funds"
POT_SHARES = "AI share picks"

PURPOSE_RETIREMENT = "Retirement"
PURPOSE_LEGACY = "Legacy"
PURPOSE_STYLES = {
    PURPOSE_RETIREMENT: {"icon": "🏖️", "label": "For your retirement", "colour": "#2B5797", "background": "#E2ECFA"},
    PURPOSE_LEGACY: {"icon": "🎁", "label": "For your family's legacy", "colour": "#7A3E9D", "background": "#F1E6F8"},
}

SAFETY_SHARE = {"low": 0.40, "mid": 0.25, "high": 0.15}
LEGACY_SAFETY_SHARE = {"low": 0.15, "mid": 0.10, "high": 0.05}
SHARES_SHARE_OF_REST = {"low": 0.30, "mid": 0.40, "high": 0.50}

POT_ROLES = {
    POT_SAFETY: "Kept safe so a bad year in the stock market never forces you to sell at a loss.",
    POT_CORE: "Spreads your money over thousands of companies and bonds worldwide for steady growth.",
    POT_SHARES: "A small set of strong, steady companies picked by the AI to add extra growth.",
}

# What each investment actually is, for the "what you own" pie chart.
ASSET_TYPES = {
    "BIL": "Cash-like savings", "SHY": "Government bonds", "TIP": "Government bonds",
    "BND": "Bonds (mixed)", "VT": "World shares fund", "VIG": "Dividend shares fund",
    "AOK": "Mixed fund", "AOM": "Mixed fund", "AOR": "Mixed fund",
}
ASSET_TYPE_EXPLANATIONS = {
    "Cash-like savings": "Very short US government loans. Almost never falls; earns roughly the interest rate.",
    "Government bonds": "Loans to the US government, paid back with interest. Steady and low risk.",
    "Bonds (mixed)": "Loans to governments and big companies. Steadier than shares; pays regular interest.",
    "World shares fund": "Small pieces of thousands of companies worldwide. Grows most over time, with ups and downs.",
    "Dividend shares fund": "Shares in companies that raise their dividends every year. Growth plus income.",
    "Company shares": "Individual companies picked by the AI. More growth potential, more ups and downs.",
    "Mixed fund": "Shares and bonds in one fund.",
}


@dataclass
class InvestorAnswers:
    name: str
    email: str
    age: int
    purpose: str                    # Retirement / Legacy / Both
    legacyShare: float              # 0–1, only used for "Both"
    totalAmount: float
    goalAmount: float
    goalYears: int
    riskLevel: str                  # low / mid / high
    experience: str                 # Never / A little / Yes, often
    incomePreference: str           # income / balanced / growth
    avoidIndustries: list = field(default_factory=list)
    notifyBuy: bool = False
    notifySell: bool = False
    notifyWeekly: bool = False


def brokerName() -> str:
    return os.getenv("BROKER_NAME", "Yahoo Finance")


def brokerLink(ticker: str) -> str:
    """Where the Invest buttons go. Set BROKER_URL_TEMPLATE in .env to your
    chosen investment platform, using {ticker} where the fund code goes."""
    template = os.getenv("BROKER_URL_TEMPLATE", "https://finance.yahoo.com/quote/{ticker}")
    return template.format(ticker=quote(ticker))


def displayName(ticker: str) -> str:
    if ticker in COMPANY_NAMES:
        return COMPANY_NAMES[ticker]
    if ticker in FUND_LIBRARY:
        return FUND_LIBRARY[ticker]["plainName"]
    return ticker


def assetTypeFor(ticker: str) -> str:
    return ASSET_TYPES.get(ticker, "Company shares")


def holdingKeyFor(holding: dict) -> str:
    return f"{holding.get('purpose', '')}:{holding['pot']}:{holding['ticker']}"


def sourcesFor(ticker: str) -> list:
    """Links to the public sources behind each recommendation."""
    sources = [("Yahoo Finance: prices, growth and dividends", f"https://finance.yahoo.com/quote/{quote(ticker)}")]
    if ticker in COMPANY_NAMES:
        sources += [
            ("SEC EDGAR: official annual reports (10-K)",
             f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={quote(ticker)}&type=10-K"),
            ("Finnhub: analyst ratings and company news", "https://finnhub.io/docs/api/recommendation-trends"),
        ]
    sources.append(("FRED (US Federal Reserve): interest rates and inflation", "https://fred.stlouisfed.org/series/DTB3"))
    return sources


def fundReason(ticker: str, pot: str, purpose: str, snapshot: dict) -> str:
    fundData = snapshot.get("funds", {}).get(ticker, {})
    facts = []
    if fundData.get("fiveYearAnnualReturn") is not None:
        facts.append(f"it grew about {fundData['fiveYearAnnualReturn']:.1%} a year over 5 years")
    if fundData.get("worstFallFromPeak") is not None:
        facts.append(f"its worst fall was {abs(fundData['worstFallFromPeak']):.0%}")
    if fundData.get("dividendYield"):
        facts.append(f"it pays about {fundData['dividendYield']:.1%} a year in income")
    factText = (" In the data, " + ", ".join(facts) + " (Yahoo Finance).") if facts else ""
    purposeText = (" Part of your retirement money, so it's chosen to be steady."
                   if purpose == PURPOSE_RETIREMENT else " Part of your legacy money, which has years to grow.")
    return f"{FUND_LIBRARY[ticker]['name']}. {POT_ROLES[pot]}{purposeText}{factText}"


def ageBasedSafety(age: int, riskLevel: str) -> float:
    """Retirement money: keep more safe as you get older, never less than
    the risk-based amount. Age 70 → at least 40%, age 80 → at least 50%."""
    return min(0.60, max(SAFETY_SHARE[riskLevel], (age - 30) / 100))


def describeInvestor(answers: InvestorAnswers) -> str:
    return (f"{answers.name}, age {answers.age}, investing ${answers.totalAmount:,.0f} for {answers.purpose.lower()}, "
            f"goal ${answers.goalAmount:,.0f} in {answers.goalYears} years. Comfort with risk: {answers.riskLevel}. "
            f"Experience: {answers.experience}. Focus: {answers.incomePreference}.")


def roundToHundred(value):
    return round(value / 100) * 100


def purposeAmounts(answers: InvestorAnswers) -> dict:
    if answers.purpose == PURPOSE_RETIREMENT:
        return {PURPOSE_RETIREMENT: answers.totalAmount}
    if answers.purpose == PURPOSE_LEGACY:
        return {PURPOSE_LEGACY: answers.totalAmount}
    legacyAmount = roundToHundred(answers.totalAmount * answers.legacyShare)
    return {PURPOSE_RETIREMENT: answers.totalAmount - legacyAmount, PURPOSE_LEGACY: legacyAmount}


def buildAdvice(answers: InvestorAnswers, snapshot: dict, fundStats) -> dict:
    """fundStats: market_data.getFundStats for every fund, used for the projection."""
    amountsByPurpose = purposeAmounts(answers)
    sharesPurpose = PURPOSE_LEGACY if PURPOSE_LEGACY in amountsByPurpose else PURPOSE_RETIREMENT

    plannedParts = []   # (purpose, pot, amount)
    for purpose, purposeAmount in amountsByPurpose.items():
        if purpose == PURPOSE_RETIREMENT:
            safetyShare = ageBasedSafety(answers.age, answers.riskLevel)
        else:
            safetyShare = LEGACY_SAFETY_SHARE[answers.riskLevel]
        safetyAmount = roundToHundred(purposeAmount * safetyShare)
        restAmount = purposeAmount - safetyAmount
        sharesAmount = roundToHundred(restAmount * SHARES_SHARE_OF_REST[answers.riskLevel]) \
            if purpose == sharesPurpose else 0
        plannedParts += [(purpose, POT_SAFETY, safetyAmount), (purpose, POT_CORE, restAmount - sharesAmount),
                         (purpose, POT_SHARES, sharesAmount)]

    sharesTotal = sum(amount for _, pot, amount in plannedParts if pot == POT_SHARES)
    stockResult = recommendStocks(sharesTotal, answers.riskLevel, describeInvestor(answers), snapshot,
                                  avoidIndustries=tuple(answers.avoidIndustries),
                                  incomePreference=answers.incomePreference)

    holdingsByKey = {}

    def addHolding(purpose, pot, ticker, amount, reason, confidence=None):
        if amount <= 0:
            return
        holding = {"purpose": purpose, "pot": pot, "ticker": ticker, "name": displayName(ticker),
                   "assetType": assetTypeFor(ticker), "amount": amount, "reason": reason,
                   "confidence": confidence, "priceAtPlan": latestPriceFor(snapshot, ticker)}
        key = holdingKeyFor(holding)
        if key in holdingsByKey:
            holdingsByKey[key]["amount"] += amount
        else:
            holdingsByKey[key] = holding

    for purpose, pot, amount in plannedParts:
        if pot == POT_SAFETY:
            for ticker, weight in UMBRELLA_BUNDLES["composite"].items():
                addHolding(purpose, pot, ticker, roundToHundred(amount * weight), fundReason(ticker, pot, purpose, snapshot))
        elif pot == POT_CORE:
            # Retirement core leans to income; legacy core follows the chosen risk level.
            riskForCore = "low" if purpose == PURPOSE_RETIREMENT and answers.riskLevel == "mid" else answers.riskLevel
            for ticker, weight in TREE_BUNDLES["composite"][riskForCore].items():
                addHolding(purpose, pot, ticker, roundToHundred(amount * weight), fundReason(ticker, pot, purpose, snapshot))
    for pick in stockResult["picks"]:
        if pick["ticker"] in FUND_LIBRARY:   # leftover that the safety limits moved into the world fund
            addHolding(sharesPurpose, POT_CORE, pick["ticker"], pick["amount"],
                       fundReason(pick["ticker"], POT_CORE, sharesPurpose, snapshot))
        else:
            addHolding(sharesPurpose, POT_SHARES, pick["ticker"], pick["amount"], pick["reason"], pick["confidence"])

    holdings = list(holdingsByKey.values())
    roundingGap = answers.totalAmount - sum(holding["amount"] for holding in holdings)
    if roundingGap:
        max((holding for holding in holdings if holding["pot"] == POT_CORE), key=lambda holding: holding["amount"])[
            "amount"] += roundingGap

    projection = projectTowardsGoal(answers, holdings, fundStats, snapshot)
    return {
        "answers": asdict(answers),
        "createdOn": date.today().isoformat(),
        "holdings": holdings,
        "purposeTotals": {purpose: sum(holding["amount"] for holding in holdings if holding["purpose"] == purpose)
                          for purpose in amountsByPurpose},
        "potTotals": {pot: sum(holding["amount"] for holding in holdings if holding["pot"] == pot)
                      for pot in (POT_SAFETY, POT_CORE, POT_SHARES)},
        "projection": projection,
        "stockSummary": stockResult["summary"],
        "stockSkipped": stockResult["skipped"],
        "stockRisks": stockResult["risks"],
        "stockAdjustments": stockResult["adjustments"],
        "stockSource": stockResult["source"],
        "boughtTickers": [],
        "inbox": [],
        "history": [{"date": date.today().isoformat(), "icon": "🌱", "text": "Plan created",
                     "detail": f"${answers.totalAmount:,.0f} towards ${answers.goalAmount:,.0f}"}],
        "valueHistory": [],
    }


def projectTowardsGoal(answers: InvestorAnswers, holdings: list, fundStats, snapshot: dict) -> dict:
    """Simulate the plan. Individual shares are modelled like the world fund (VT),
    which keeps the projection honest rather than optimistic."""
    safetyHoldings, growthHoldings = {}, {}
    for holding in holdings:
        target = safetyHoldings if holding["pot"] == POT_SAFETY else growthHoldings
        ticker = holding["ticker"] if holding["ticker"] in FUND_LIBRARY else "VT"
        target[ticker] = target.get(ticker, 0) + holding["amount"]
    planForSimulation = Plan(sum(safetyHoldings.values()), sum(growthHoldings.values()),
                             safetyHoldings, growthHoldings, {}, [])
    result = simulateFuture(planForSimulation, fundStats, years=answers.goalYears, careYears=0,
                            inflationRate=snapshot["economy"]["inflationRate"], targetValue=answers.goalAmount)
    allSimulated = {}
    for holdingsGroup in (safetyHoldings, growthHoldings):
        for ticker, amount in holdingsGroup.items():
            allSimulated[ticker] = allSimulated.get(ticker, 0) + amount
    expectedReturn = sum(fundStats.loc[ticker, "annualReturn"] * amount
                         for ticker, amount in allSimulated.items()) / answers.totalAmount
    requiredReturn = (answers.goalAmount / answers.totalAmount) ** (1 / answers.goalYears) - 1
    return {
        "chanceOfReachingGoal": result["chanceOfReachingTarget"],
        "typicalFinalValue": result["typicalFinalValue"],
        "badFinalValue": result["badFinalValue"],
        "expectedReturn": float(expectedReturn),
        "requiredReturn": float(requiredReturn),
        "bands": result["totalBands"].to_dict(orient="list"),
    }
