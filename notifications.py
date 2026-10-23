"""
notifications.py — the weekly update and alerts, in the app inbox and by email.

Email uses plain SMTP, so any provider works. For Gmail: turn on 2-step
verification, create an "App password", and put it in .env as SMTP_PASSWORD.
"""

import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

import advisor
from portfolio import brokerLink, displayName
from signals import holdingCurrentValues, signalFromIndicators
from stock_advisor import scoreStocks

ALERT_ICONS = {"buy": "🟢", "sell": "🟠", "wait": "🟡", "rebalance": "⚖️", "watch": "👀"}


def bestIdeasThisWeek(profile: dict, snapshot: dict, howMany=3) -> list:
    """Highest-scoring shares that suit the client and aren't showing a warning."""
    avoided = set(profile["answers"].get("avoidIndustries", []))
    allowedSnapshot = {**snapshot, "stocks": {ticker: data for ticker, data in snapshot["stocks"].items()
                                              if data["industry"] not in avoided}}
    scores = scoreStocks(allowedSnapshot)
    ideas = []
    for ticker in sorted(scores, key=scores.get, reverse=True):
        indicators = allowedSnapshot["stocks"][ticker].get("yahooFinance", {})
        signal = signalFromIndicators(indicators)
        if signal and signal["action"] in ("sell", "wait"):
            continue
        ideas.append({"ticker": ticker, "name": displayName(ticker), "score": scores[ticker],
                      "dividendYield": indicators.get("dividendYield"),
                      "onSale": bool(signal and signal["action"] == "buy"), "link": brokerLink(ticker)})
        if len(ideas) == howMany:
            break
    return ideas


def buildWeeklyDigest(profile: dict, snapshot: dict, alerts: list) -> dict:
    valuedHoldings = holdingCurrentValues(profile["holdings"], snapshot, profile.get("purchases", {}))
    valueNow = sum(holding["currentValue"] for holding in valuedHoldings)
    valueAtStart = sum(holding["amount"] for holding in valuedHoldings)
    ideas = bestIdeasThisWeek(profile, snapshot)
    firstName = profile["answers"]["name"].split(" ")[0]

    facts = (f"Savings now ${valueNow:,.0f} (started ${valueAtStart:,.0f}). {len(alerts)} alerts. "
             f"Top ideas: {', '.join(idea['name'] for idea in ideas)}. "
             f"Interest rate {snapshot['economy']['cashRate']:.1%}, inflation {snapshot['economy']['inflationRate']:.1%}.")
    introduction = advisor.askModel(
        f"Write a warm 2-sentence opening for a beginner investor's weekly update. "
        f"Plain words, no hype, no promises. Facts: {facts}", useQuickModel=True)
    if not introduction or introduction.startswith("_("):
        change = valueNow / valueAtStart - 1
        changeWords = "holding steady" if abs(change) < 0.002 else ("up" if change > 0 else "down") + f" {abs(change):.1%}"
        introduction = (f"Your savings are {changeWords} at ${valueNow:,.0f} this week. "
                        "Here's what's worth knowing, in plain English.")

    return {"date": date.today().isoformat(), "subject": f"🌳 Your Heirloom update, {firstName}",
            "introduction": introduction, "valueNow": valueNow, "valueAtStart": valueAtStart,
            "ideas": ideas, "alerts": alerts}


def digestAsText(digest: dict) -> str:
    lines = [digest["introduction"], "", "THIS WEEK'S BEST IDEAS"]
    for idea in digest["ideas"]:
        lines.append(f"- {idea['name']} ({idea['ticker']}), steadiness {idea['score']}/100"
                     + (" · on sale" if idea["onSale"] else "") + f"  {idea['link']}")
    lines += ["", "ALERTS"] + ([f"- {alert['title']}: {alert['message']}" for alert in digest["alerts"]]
                               or ["- Nothing needs your attention this week."])
    lines += ["", "Educational hackathon project. Not financial advice."]
    return "\n".join(lines)


def digestAsHtml(digest: dict) -> str:
    buttonStyle = ("display:inline-block;background:#3E8E5E;color:#fff;padding:10px 16px;"
                   "border-radius:10px;text-decoration:none;font-size:17px")
    ideaRows = "".join(
        f"<p style='font-size:19px'><b>{escape(idea['name'])}</b> ({idea['ticker']}) · steadiness {idea['score']}/100"
        f"{' · 🏷️ on sale' if idea['onSale'] else ''}<br><a style='{buttonStyle}' href='{idea['link']}'>View &amp; buy ↗</a></p>"
        for idea in digest["ideas"])
    alertRows = "".join(
        f"<p style='font-size:18px'>{ALERT_ICONS.get(alert['type'], '•')} <b>{escape(alert['title'])}</b><br>"
        f"{escape(alert['message'])}</p>" for alert in digest["alerts"]) or \
        "<p style='font-size:18px'>✅ Nothing needs your attention this week.</p>"
    return f"""<div style="font-family:Arial,sans-serif;max-width:560px;color:#1F2A24">
      <h1 style="color:#3E8E5E">🌳 Heirloom</h1>
      <p style="font-size:20px">{escape(digest['introduction'])}</p>
      <h2>This week's best ideas</h2>{ideaRows}
      <h2>Alerts</h2>{alertRows}
      <p style="font-size:14px;color:#777">Educational hackathon project. Not financial advice.
      Signals are based on past prices and can be wrong.</p></div>"""


def emailIsConfigured() -> bool:
    return all(os.getenv(name) for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def sendEmail(toAddress: str, subject: str, htmlBody: str, textBody: str):
    """Returns (succeeded, message)."""
    if not emailIsConfigured():
        return False, "Email isn't set up yet (add SMTP settings to .env)."
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER"))
    message["To"] = toAddress
    message.attach(MIMEText(textBody, "plain"))
    message.attach(MIMEText(htmlBody, "html"))
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")  # Gmail shows app passwords with spaces
    preferredPort = int(os.getenv("SMTP_PORT", "587"))
    lastError = None
    # Some Wi-Fi networks block one email port, so try the other one too.
    for port in dict.fromkeys([preferredPort, 465, 587]):
        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                server.starttls()
            with server:
                server.login(user, password)
                server.send_message(message)
            return True, f"Sent to {toAddress}"
        except smtplib.SMTPAuthenticationError:
            return False, ("Gmail rejected the login. Use a 16-letter App password "
                           "(Google Account → Security → App passwords), not your normal password.")
        except Exception as error:
            lastError = error
    return False, (f"Email failed: {lastError}. This Wi-Fi may be blocking email; "
                   "try a phone hotspot.")
