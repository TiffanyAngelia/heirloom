"""
simulator.py — "what might happen?"

1. replayScenario: run the plan through a real historical period
   (e.g. the 2008 crash) using actual daily prices.
2. simulateFuture: thousands of possible futures (Monte Carlo), with care
   costs paid from the Umbrella first and topped up from the Tree in good years.
"""

import numpy as np
import pandas as pd

from market_data import expandToReplayTickers, getPriceHistory

SCENARIOS = {
    "2008 financial crisis": {"start": "2007-10-01", "end": "2012-12-31", "mood": "bad",
                              "story": "Banks collapsed and world stock markets roughly halved."},
    "2020 Covid crash": {"start": "2020-01-02", "end": "2021-06-30", "mood": "bad",
                         "story": "Markets fell fast in March 2020, then bounced back within months."},
    "2022 inflation shock": {"start": "2022-01-03", "end": "2023-12-29", "mood": "bad",
                             "story": "Prices rose quickly and both stocks and bonds fell at the same time."},
    "2016–2019 good years": {"start": "2016-01-04", "end": "2019-12-31", "mood": "good",
                             "story": "A long, calm stretch where markets rose steadily."},
}


def replayScenario(holdings: dict, startDate: str, endDate: str) -> pd.Series:
    """Daily value of a buy-and-hold pot over a real historical period."""
    replayHoldings = expandToReplayTickers(holdings)
    prices = getPriceHistory(list(replayHoldings), startDate, endDate).dropna()
    growthSinceStart = prices / prices.iloc[0]
    dailyValue = sum(growthSinceStart[ticker] * amount
                     for ticker, amount in replayHoldings.items())
    return dailyValue.rename("value")


def summariseReplay(dailyValue: pd.Series) -> dict:
    startValue = dailyValue.iloc[0]
    lowestValue = dailyValue.min()
    lowestDate = dailyValue.idxmin()
    afterLowest = dailyValue.loc[lowestDate:]
    recovered = afterLowest[afterLowest >= startValue]
    recoveryMonths = None
    if not recovered.empty:
        recoveryMonths = round((recovered.index[0] - lowestDate).days / 30.4)
    return {
        "startValue": startValue,
        "lowestValue": lowestValue,
        "worstDrop": lowestValue / startValue - 1,
        "lowestDate": lowestDate,
        "recoveryMonths": recoveryMonths,
        "endValue": dailyValue.iloc[-1],
    }


def potReturnAndVolatility(holdings: dict, fundStats: pd.DataFrame):
    totalAmount = sum(holdings.values())
    expectedReturn = sum(fundStats.loc[ticker, "annualReturn"] * amount
                         for ticker, amount in holdings.items()) / totalAmount
    volatility = sum(fundStats.loc[ticker, "annualVolatility"] * amount
                     for ticker, amount in holdings.items()) / totalAmount
    return expectedReturn, volatility


def simulateFuture(plan, fundStats, years=20, yearlyCareCost=15_000,
                   careStartYear=5, careYears=4, inflationRate=0.03,
                   simulations=2000, seed=42, targetValue=None) -> dict:
    randomGenerator = np.random.default_rng(seed)
    umbrellaReturn, umbrellaVolatility = potReturnAndVolatility(plan.umbrellaHoldings, fundStats)
    treeReturn, treeVolatility = potReturnAndVolatility(plan.treeHoldings, fundStats)

    umbrellaValues = np.zeros((simulations, years + 1))
    treeValues = np.zeros((simulations, years + 1))
    umbrellaValues[:, 0] = plan.umbrellaAmount
    treeValues[:, 0] = plan.treeAmount
    careWasFullyPaid = np.ones(simulations, dtype=bool)
    treeWasTouchedForCare = np.zeros(simulations, dtype=bool)

    for year in range(1, years + 1):
        umbrellaGrowth = randomGenerator.normal(umbrellaReturn, umbrellaVolatility, simulations)
        treeGrowth = randomGenerator.normal(treeReturn, treeVolatility, simulations)
        umbrella = umbrellaValues[:, year - 1] * (1 + umbrellaGrowth)
        tree = treeValues[:, year - 1] * (1 + treeGrowth)

        isCareYear = careStartYear <= year < careStartYear + careYears
        if isCareYear:
            careBill = yearlyCareCost * (1 + inflationRate) ** year
            paidFromUmbrella = np.minimum(umbrella, careBill)
            umbrella -= paidFromUmbrella
            stillOwed = careBill - paidFromUmbrella
            treeWasTouchedForCare |= stillOwed > 0
            paidFromTree = np.minimum(tree, stillOwed)
            tree -= paidFromTree
            careWasFullyPaid &= (stillOwed - paidFromTree) <= 0.01

            # Bucket rule: in years the Tree grew, move some gains back into the
            # Umbrella so it holds ~2 years of care. Never sell the Tree after a fall.
            umbrellaTarget = 2 * careBill
            treeGain = np.maximum(treeValues[:, year - 1] * treeGrowth, 0)
            topUp = np.where(treeGrowth > 0,
                             np.minimum(treeGain, np.maximum(umbrellaTarget - umbrella, 0)), 0)
            tree -= topUp
            umbrella += topUp

        umbrellaValues[:, year] = np.maximum(umbrella, 0)
        treeValues[:, year] = np.maximum(tree, 0)

    totalValues = umbrellaValues + treeValues
    percentiles = lambda values: pd.DataFrame({
        "year": np.arange(years + 1),
        "bad (1 in 10)": np.percentile(values, 10, axis=0),
        "typical": np.percentile(values, 50, axis=0),
        "good (1 in 10)": np.percentile(values, 90, axis=0),
    })
    goalResult = {}
    if targetValue:
        reachedGoal = totalValues >= targetValue
        goalResult = {
            "chanceOfReachingTarget": float(reachedGoal[:, -1].mean()),
            "chanceOfReachingTargetEver": float(reachedGoal.any(axis=1).mean()),
            "typicalFinalValue": float(np.median(totalValues[:, -1])),
            "badFinalValue": float(np.percentile(totalValues[:, -1], 10)),
        }
    return {
        **goalResult,
        "totalBands": percentiles(totalValues),
        "treeBands": percentiles(treeValues),
        "chanceCareFullyPaid": careWasFullyPaid.mean(),
        "chanceUmbrellaWasEnough": 1 - treeWasTouchedForCare.mean(),
        "typicalLegacy": float(np.median(treeValues[:, -1])),
        "badLegacy": float(np.percentile(treeValues[:, -1], 10)),
        "assumptions": {
            "umbrellaReturn": umbrellaReturn, "umbrellaVolatility": umbrellaVolatility,
            "treeReturn": treeReturn, "treeVolatility": treeVolatility,
        },
    }
