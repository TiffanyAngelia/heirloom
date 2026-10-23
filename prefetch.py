"""
Run this while you have good Wi-Fi, BEFORE the demo:
    python prefetch.py
It downloads every price series the app needs into data/cache/, so the
demo works even if the internet drops.
"""

from dotenv import load_dotenv

from market_data import getCurrentRates, getFundStats
from planner import TREE_BUNDLES, UMBRELLA_BUNDLES, ClientAnswers, buildPlan
from simulator import SCENARIOS, replayScenario

load_dotenv()

allTickers = set()
for bundle in UMBRELLA_BUNDLES.values():
    allTickers.update(bundle)
for styleBundles in TREE_BUNDLES.values():
    for bundle in styleBundles.values():
        allTickers.update(bundle)

print("Fetching 10-year stats for:", ", ".join(sorted(allTickers)))
print(getFundStats(sorted(allTickers)).round(4))
print("Rates:", getCurrentRates())

for riskLevel in ["low", "mid", "high"]:
    for bundleStyle in ["single", "composite"]:
        plan = buildPlan(ClientAnswers(riskLevel=riskLevel, bundleStyle=bundleStyle))
        for scenarioName, scenario in SCENARIOS.items():
            for holdings in (plan.umbrellaHoldings, plan.treeHoldings):
                replayScenario(holdings, scenario["start"], scenario["end"])
        print(f"Cached replays for {riskLevel}/{bundleStyle}")

print("Done. The app will now work offline for these plans.")
