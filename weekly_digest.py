"""
Sends every client their update.

    python weekly_digest.py            # weekly update to everyone who opted in
    python weekly_digest.py --alerts   # only clients with buy/sell/rebalance alerts today

Schedule it with .github/workflows/notifications.yml (or cron on a server).
"""

import sys

from dotenv import load_dotenv

from notifications import buildWeeklyDigest, digestAsHtml, digestAsText, sendEmail
from portfolio import brokerLink
from signals import buildAlerts
from stock_data import buildSnapshot
from users import addToInbox, listProfiles

load_dotenv()

alertsOnly = "--alerts" in sys.argv
snapshot = buildSnapshot(useCache=False)

for profile in listProfiles():
    answers = profile["answers"]
    alerts = buildAlerts(profile, snapshot, brokerLink)
    # Only the alert types this person signed up for
    wantedTypes = ({"buy", "watch"} if answers.get("notifyBuy") else set()) | \
                  ({"sell", "rebalance"} if answers.get("notifySell") else set())
    chosenAlerts = [alert for alert in alerts if alert["type"] in wantedTypes]
    if alertsOnly and not chosenAlerts:
        continue
    if not alertsOnly and not answers.get("notifyWeekly"):
        continue

    digest = buildWeeklyDigest(profile, snapshot, chosenAlerts)
    if alertsOnly:
        digest["subject"] = f"🔔 Heirloom: {chosenAlerts[0]['title']}"
    addToInbox(profile, digest)
    succeeded, message = sendEmail(answers["email"], digest["subject"], digestAsHtml(digest), digestAsText(digest))
    print(f"{answers['email']}: {message}")
