"""
planner.py — turns Joan and Pat's answers into a two-pot plan.

Umbrella = short-term, safe money for care costs and surprises.
Tree     = long-term money for growth and the grandchildren.

All tickers are real, widely held US-listed ETFs so yfinance can price them.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Fund library. Fallback returns/volatility are long-run planning assumptions,
# used only when live data can't be fetched. The UI labels them as such.
# ---------------------------------------------------------------------------
FUND_LIBRARY = {
    "BIL": {"name": "US Treasury bills (1–3 months)", "plainName": "Cash-like government savings",
            "fallbackReturn": 0.035, "fallbackVolatility": 0.005},
    "SHY": {"name": "Short-term US Treasuries (1–3 years)", "plainName": "Short-term government bonds",
            "fallbackReturn": 0.037, "fallbackVolatility": 0.02},
    "TIP": {"name": "Inflation-protected Treasuries", "plainName": "Bonds that rise with prices",
            "fallbackReturn": 0.035, "fallbackVolatility": 0.06},
    "BND": {"name": "Total US bond market", "plainName": "A mix of high-quality bonds",
            "fallbackReturn": 0.04, "fallbackVolatility": 0.06},
    "VIG": {"name": "Dividend growth companies", "plainName": "Steady companies that raise dividends",
            "fallbackReturn": 0.07, "fallbackVolatility": 0.14},
    "VT":  {"name": "Total world stock market", "plainName": "Thousands of companies worldwide",
            "fallbackReturn": 0.07, "fallbackVolatility": 0.16},
    "AOK": {"name": "iShares Conservative Allocation", "plainName": "All-in-one fund (cautious)",
            "fallbackReturn": 0.045, "fallbackVolatility": 0.07},
    "AOM": {"name": "iShares Moderate Allocation", "plainName": "All-in-one fund (balanced)",
            "fallbackReturn": 0.055, "fallbackVolatility": 0.09},
    "AOR": {"name": "iShares Growth Allocation", "plainName": "All-in-one fund (growth)",
            "fallbackReturn": 0.065, "fallbackVolatility": 0.12},
}

# Investment bundles: "composite" = several funds, "single" = one simple fund.
UMBRELLA_BUNDLES = {
    "composite": {"BIL": 0.40, "SHY": 0.40, "TIP": 0.20},
    "single": {"SHY": 1.00},
}

TREE_BUNDLES = {
    "composite": {
        "low":  {"VT": 0.45, "VIG": 0.20, "BND": 0.35},
        "mid":  {"VT": 0.60, "VIG": 0.20, "BND": 0.20},
        "high": {"VT": 0.80, "VIG": 0.10, "BND": 0.10},
    },
    "single": {
        "low":  {"AOK": 1.00},
        "mid":  {"AOM": 1.00},
        "high": {"AOR": 1.00},
    },
}

# Base share of money kept in the umbrella, by risk comfort.
BASE_UMBRELLA_SHARE = {"low": 0.55, "mid": 0.40, "high": 0.30}


@dataclass
class ClientAnswers:
    names: str = "Joan and Pat"
    ages: str = "70 and 72"
    totalAmount: float = 100_000
    forWhom: list = field(default_factory=lambda: ["Ourselves", "Grandchildren"])
    purposes: list = field(default_factory=lambda: ["Care costs", "Leave something behind"])
    riskLevel: str = "low"                 # low / mid / high
    bundleStyle: str = "composite"         # composite / single
    yearsUntilCareMightStart: int = 5
    yearlyCareCost: float = 15_000
    grandchildNames: list = field(default_factory=lambda: ["Ella", "Sam"])
    yearsForGrandchildren: int = 15
    # Account and preferences (sign-up screens)
    email: str = ""
    experience: str = "A little"                     # Never / A little / Yes, often
    topPriority: str = "Care costs"
    monthlyWithdrawal: float = 0
    giveNowOrLater: str = "Later"
    avoidIndustries: list = field(default_factory=list)
    incomePreference: str = "balanced"               # income / balanced / growth
    wantsWeeklyEmail: bool = True
    familyHelperEmail: str = ""


@dataclass
class Plan:
    umbrellaAmount: float
    treeAmount: float
    umbrellaHoldings: dict       # ticker -> dollars
    treeHoldings: dict           # ticker -> dollars
    grandchildShares: dict       # name -> dollars of the tree
    reasons: list                # plain-English reasons (template, before AI rewrites)


def roundToHundred(value):
    return round(value / 100) * 100


def buildPlan(answers: ClientAnswers) -> Plan:
    """Rule-based split. Rules are deliberately simple so judges can follow them;
    the AI layer explains and stress-tests them, it doesn't invent them."""
    reasons = []
    umbrellaShare = BASE_UMBRELLA_SHARE[answers.riskLevel]
    reasons.append(
        f"You chose **{answers.riskLevel}** risk, so we start by keeping "
        f"{umbrellaShare:.0%} of your money safe in the Umbrella."
    )

    if "Care costs" in answers.purposes:
        # Aim to hold enough for ~3 years of care in the umbrella.
        careCushion = answers.yearlyCareCost * 3
        cushionShare = careCushion / answers.totalAmount
        if cushionShare > umbrellaShare:
            umbrellaShare = cushionShare
            reasons.append(
                f"Care could cost about ${answers.yearlyCareCost:,.0f} a year, so we keep "
                f"around three years of it (${careCushion:,.0f}) ready in the Umbrella."
            )
        if answers.yearsUntilCareMightStart <= 3:
            umbrellaShare += 0.10
            reasons.append(
                "Care might be needed within 3 years, so we add an extra 10% to the Umbrella. "
                "Money you may need soon shouldn't depend on the stock market."
            )

    if "Grandchildren" not in answers.forWhom and "Leave something behind" not in answers.purposes:
        umbrellaShare += 0.05
        reasons.append("This money is mainly for yourselves, so we lean a little safer.")

    umbrellaShare = min(max(umbrellaShare, 0.20), 0.80)
    umbrellaAmount = roundToHundred(answers.totalAmount * umbrellaShare)
    treeAmount = answers.totalAmount - umbrellaAmount

    umbrellaWeights = UMBRELLA_BUNDLES[answers.bundleStyle]
    treeWeights = TREE_BUNDLES[answers.bundleStyle][answers.riskLevel]

    umbrellaHoldings = {ticker: roundToHundred(umbrellaAmount * weight)
                        for ticker, weight in umbrellaWeights.items()}
    treeHoldings = {ticker: roundToHundred(treeAmount * weight)
                    for ticker, weight in treeWeights.items()}
    fixRounding(umbrellaHoldings, umbrellaAmount)
    fixRounding(treeHoldings, treeAmount)

    reasons.append(
        f"The Tree (${treeAmount:,.0f}) has {answers.yearsForGrandchildren}+ years to grow, "
        "so it can ride out bad years in the market."
    )

    grandchildShares = {}
    if answers.grandchildNames:
        sharePerChild = treeAmount / len(answers.grandchildNames)
        grandchildShares = {name: sharePerChild for name in answers.grandchildNames}

    return Plan(umbrellaAmount, treeAmount, umbrellaHoldings, treeHoldings,
                grandchildShares, reasons)


def fixRounding(holdings: dict, targetTotal: float):
    """Make sure rounded holdings still add up exactly to the pot size."""
    difference = targetTotal - sum(holdings.values())
    largestTicker = max(holdings, key=holdings.get)
    holdings[largestTicker] += difference


def allHoldings(plan: Plan) -> dict:
    combined = dict(plan.umbrellaHoldings)
    for ticker, amount in plan.treeHoldings.items():
        combined[ticker] = combined.get(ticker, 0) + amount
    return combined
