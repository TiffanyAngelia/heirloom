"""
Heirloom — your AI investment analyst, designed to be easy for older investors.
Run with:  streamlit run app.py

Welcome → Sign up (6 short screens, nothing pre-filled) → plan built instantly → dashboard
Dashboard tabs: Home · Plan · History · Ask · Alerts
Accessibility on every screen: text size (A / A+ / A++), high contrast, and 🔊 read aloud.
"""

import json

import altair as alt
import pandas as pd
import streamlit as st

import advisor
import ui
from history import backtestPlan, logEvent, recordValue
from market_data import getFundStats
from notifications import buildWeeklyDigest, digestAsHtml, digestAsText, emailIsConfigured, sendEmail
from planner import FUND_LIBRARY
from portfolio import (ASSET_TYPE_EXPLANATIONS, POT_CORE, POT_ROLES, POT_SAFETY, POT_SHARES, PURPOSE_LEGACY,
                       PURPOSE_RETIREMENT, PURPOSE_STYLES, InvestorAnswers, brokerLink, brokerName, buildAdvice,
                       holdingKeyFor, sourcesFor)
from signals import buildAlerts, historicalSignals, holdingCurrentValues
from stock_advisor import INDICATOR_LABELS, flattenStock
from stock_data import CANDIDATE_STOCKS, buildSnapshot, latestPriceFor, loadPriceHistory
from updates import buildUpdates
from users import addToInbox, loadProfile, saveProfile

st.set_page_config(page_title="Heirloom", page_icon="🌳", layout="centered")
ui.applyTheme()

POT_ICONS = {POT_SAFETY: "🛡️", POT_CORE: "🌍", POT_SHARES: "🤖"}
ASSET_COLOURS = {"Cash-like savings": "#CDE8D8", "Government bonds": "#8CC7A1", "Bonds (mixed)": "#4FA374",
                 "World shares fund": "#0B5D3B", "Dividend shares fund": "#7FD33F", "Company shares": "#B8F35A",
                 "Mixed fund": "#2C8A5F"}


# ---------------------------------------------------------------------------
# Cached data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cachedSnapshot():
    return buildSnapshot()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cachedPrices():
    return loadPriceHistory()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cachedFundStats():
    return getFundStats(list(FUND_LIBRARY))


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
EMPTY_FORM = {"name": "", "email": "", "age": None, "purpose": None, "legacyShare": None, "totalAmount": None,
              "goalAmount": None, "goalYears": None, "riskLevel": None, "experience": None,
              "incomePreference": None, "avoidIndustries": [], "notifyBuy": False, "notifySell": False,
              "notifyWeekly": False}
DEFAULT_SETTINGS = {"textSize": "A+", "highContrast": False, "speechRate": "Normal"}

if "page" not in st.session_state:
    st.session_state.page = "welcome"
    st.session_state.signupStep = 0
    st.session_state.form = dict(EMPTY_FORM)
    st.session_state.profile = None
    st.session_state.chatHistory = []
    st.session_state.settings = dict(DEFAULT_SETTINGS)

form = st.session_state.form
settings = st.session_state.settings
speechRate = ui.SPEECH_RATES[settings["speechRate"]]


def saveSettings():
    if st.session_state.profile:
        st.session_state.profile["settings"] = dict(settings)
        saveProfile(st.session_state.profile)


# ---------------------------------------------------------------------------
# Accessibility bar (top of every screen)
# ---------------------------------------------------------------------------
ui.applyAccessibility(settings["textSize"], settings["highContrast"])
sizeColumn, contrastColumn = st.columns([3, 2])
chosenSize = sizeColumn.segmented_control("Text size", list(ui.TEXT_SIZES), default=settings["textSize"],
                                          key="textSizeControl")
if chosenSize and chosenSize != settings["textSize"]:
    settings["textSize"] = chosenSize
    saveSettings()
    st.rerun()
chosenContrast = contrastColumn.toggle("High contrast", value=settings["highContrast"])
if chosenContrast != settings["highContrast"]:
    settings["highContrast"] = chosenContrast
    saveSettings()
    st.rerun()


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
def pageHeader(title: str, speechText: str, key: str):
    st.header(title)
    ui.speakButton(speechText, key, speechRate, label="🔊 Read this screen to me")


def radioChoice(label, options: dict, currentValue, horizontal=False):
    """Radio with nothing selected until the person picks. options: {label: value}."""
    values = list(options.values())
    picked = st.radio(label, list(options), index=values.index(currentValue) if currentValue in values else None,
                      horizontal=horizontal)
    return options[picked] if picked else None


def stepButtons(errorMessage, nextLabel="Next  →"):
    backColumn, nextColumn = st.columns(2)
    if st.session_state.signupStep > 0 and backColumn.button("←  Back", use_container_width=True):
        st.session_state.signupStep -= 1
        st.rerun()
    if nextColumn.button(nextLabel, type="primary", use_container_width=True):
        if errorMessage:
            st.error(errorMessage)
        else:
            st.session_state.signupStep += 1
            st.rerun()


def priceChart(ticker: str, priceHistory: pd.DataFrame, days=365):
    if ticker not in priceHistory:
        st.caption("Price chart appears once market data is downloaded.")
        return
    prices = priceHistory[ticker].dropna()
    chartFrame = pd.DataFrame({"Date": prices.index, "Price": prices.values,
                               "Usual price": prices.rolling(200).mean().values})
    chartFrame = chartFrame[chartFrame["Date"] >= chartFrame["Date"].max() - pd.Timedelta(days=days)]
    priceLine = alt.Chart(chartFrame).mark_line(strokeWidth=3, color=ui.DEEP_GREEN).encode(
        x=alt.X("Date:T", title=None), y=alt.Y("Price:Q", title="Price ($)", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("Date:T"), alt.Tooltip("Price:Q", format="$,.2f")])
    usualLine = alt.Chart(chartFrame).mark_line(strokeDash=[6, 4], color="#999").encode(x="Date:T", y="Usual price:Q")
    markers = historicalSignals(prices)
    markers = markers[markers["Date"] >= chartFrame["Date"].min()]
    markerLayer = alt.Chart(markers).mark_point(size=220, filled=True).encode(
        x="Date:T", y="Price:Q",
        shape=alt.Shape("Signal:N", scale=alt.Scale(domain=["buy", "sell"], range=["triangle-up", "triangle-down"]),
                        legend=None),
        color=alt.Color("Signal:N", scale=alt.Scale(domain=["buy", "sell"], range=["#2E9E4F", "#E08E2B"]), legend=None),
        tooltip=[alt.Tooltip("Date:T"), "Signal:N"])
    st.altair_chart((priceLine + usualLine + markerLayer).properties(height=230), use_container_width=True)
    st.caption("Green line: price over the last year. Dashed: its usual price (200-day average). "
               "▲ past smart times to buy, ▼ past times to take profit.")


GRADE_RULES = {
    "annualVolatility": (lambda value: value < 0.18, lambda value: value < 0.28),
    "worstFallFromPeak": (lambda value: value > -0.25, lambda value: value > -0.40),
    "dividendYield": (lambda value: value > 0.025, lambda value: value > 0.01),
    "fiveYearAnnualReturn": (lambda value: value > 0.07, lambda value: value > 0.03),
    "analystBuyShare": (lambda value: value > 0.6, lambda value: value > 0.4),
    "profitMargin": (lambda value: value > 0.15, lambda value: value > 0.07),
    "priceToEarnings": (lambda value: value < 20, lambda value: value < 30),
    "debtToEquity": (lambda value: value < 1, lambda value: value < 2),
}


def reportCard(ticker: str, snapshot: dict):
    stockData = snapshot["stocks"].get(ticker)
    fundData = snapshot.get("funds", {}).get(ticker, {})
    flatIndicators = flattenStock(stockData) if stockData else {
        key: fundData.get(key) for key in ("fiveYearAnnualReturn", "annualVolatility", "worstFallFromPeak",
                                           "dividendYield")}
    rows = []
    for measure, value in flatIndicators.items():
        if value is None or (measure == "dividendYield" and not value):
            continue
        isGood, isOk = GRADE_RULES[measure]
        grade = "🟢" if isGood(value) else "🟡" if isOk(value) else "🟠"
        shown = f"{value:.1f}" if measure in ("priceToEarnings", "debtToEquity") else f"{value:.1%}"
        rows.append({"": grade, "Key indicator": INDICATOR_LABELS[measure], "Value": shown})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("🟢 strong · 🟡 fine · 🟠 worth watching")


def whyThisOne(ticker: str, reason: str, snapshot: dict, priceHistory: pd.DataFrame):
    if reason:
        st.markdown(f"**Why:** {reason}")
    priceChart(ticker, priceHistory)
    reportCard(ticker, snapshot)
    headlines = snapshot["stocks"].get(ticker, {}).get("finnhub", {}).get("recentHeadlines", [])
    if headlines:
        st.markdown("**Recent news the AI read** (Finnhub)")
        for headline in headlines[:3]:
            linkText = f"[{headline['headline']}]({headline['url']})" if headline.get("url") else headline["headline"]
            st.markdown(f"- {headline['date']} · {headline['source']}: {linkText}")
    st.markdown("**Sources**")
    st.markdown("\n".join(f"- [{label}]({url})" for label, url in sourcesFor(ticker)))


def donutChart(frame: pd.DataFrame, categoryColumn: str, colours: dict, height=300):
    total = frame["Amount"].sum()
    frame = frame.assign(Label=frame.apply(
        lambda row: f"{row[categoryColumn]}  ${row['Amount']:,.0f} ({row['Amount'] / total:.0%})", axis=1))
    chart = alt.Chart(frame).mark_arc(innerRadius=60, outerRadius=118, cornerRadius=4, stroke="white",
                                      strokeWidth=2).encode(
        theta="Amount:Q",
        color=alt.Color("Label:N", scale=alt.Scale(domain=list(frame["Label"]),
                                                   range=[colours.get(name, "#999") for name in frame[categoryColumn]]),
                        legend=alt.Legend(orient="bottom", direction="vertical", title=None, labelFontSize=15,
                                          labelLimit=400, symbolSize=200)),
        tooltip=[alt.Tooltip(f"{categoryColumn}:N"), alt.Tooltip("Amount:Q", format="$,.0f")])
    st.altair_chart(chart.properties(height=height), use_container_width=True)


page = st.session_state.page

# ---------------------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------------------
if page == "welcome":
    st.markdown("<div style='font-size:22px;font-weight:800;color:#0B5D3B'>🌳 Heirloom</div>", unsafe_allow_html=True)
    ui.welcomeBanner()
    ui.speakButton("Welcome to Heirloom. Tell us your goal, and our AI will tell you what to invest in, how much, "
                   "and when. Press Get started to begin. You can make the text bigger with the A buttons at the top.",
                   "welcome", speechRate, label="🔊 Read this screen to me")
    ui.tilesCard("What you get", [("🎯", "Goal plan", "In 1 min"), ("🤖", "AI picks", "Explained"),
                                  ("🔔", "Smart alerts", "By email"), ("💬", "Ask AI", "Any time")])
    if st.button("✨  Get started", type="primary", use_container_width=True):
        st.session_state.page = "signup"
        st.rerun()
    with st.expander("Already have a plan? Log in"):
        returningEmail = st.text_input("Your email")
        if st.button("Open my plan", use_container_width=True) and returningEmail:
            savedProfile = loadProfile(returningEmail)
            if savedProfile and "purposeTotals" in savedProfile:
                st.session_state.profile = savedProfile
                st.session_state.settings.update(savedProfile.get("settings", {}))
                st.session_state.page = "dashboard"
                st.rerun()
            st.error("We couldn't find a plan for that email. If you signed up on an older version, please sign up again.")

# ---------------------------------------------------------------------------
# Sign up — nothing pre-filled; each screen checks its answers
# ---------------------------------------------------------------------------
elif page == "signup":
    signupStep = st.session_state.signupStep
    totalSteps = 6
    if signupStep < totalSteps:
        st.progress((signupStep + 1) / totalSteps, text=f"Step {signupStep + 1} of {totalSteps}")

    if signupStep == 0:
        pageHeader("👋 About you", "About you. Please type your name, your email, and your age.", "step0")
        form["name"] = st.text_input("Your name", form["name"], placeholder="e.g. Maria")
        form["email"] = st.text_input("Your email", form["email"], placeholder="name@example.com",
                                      help="For your alerts. We never share it.")
        form["age"] = st.number_input("Your age", min_value=18, max_value=110, value=form["age"], step=1,
                                      placeholder="e.g. 68")
        problem = None if form["name"].strip() and "@" in form["email"] and form["age"] \
            else "Please add your name, email and age."
        stepButtons(problem)

    elif signupStep == 1:
        pageHeader("🧭 Who is this money for?",
                   "Who is this money for? Choose: your own retirement, which is money to live on. "
                   "A legacy for your family, which is money to pass on. Or both.", "step1")
        form["purpose"] = radioChoice("Choose one", {
            "🏖️  My own retirement: money to live on": PURPOSE_RETIREMENT,
            "🎁  A legacy for my family: money to pass on": PURPOSE_LEGACY,
            "⚖️  Both": "Both"}, form["purpose"])
        for purpose in (PURPOSE_RETIREMENT, PURPOSE_LEGACY):
            style = PURPOSE_STYLES[purpose]
            explanation = ("Kept steadier, with more safety and regular income, because you may need it soon."
                           if purpose == PURPOSE_RETIREMENT else
                           "Can grow for longer, so more goes into growth, including the AI's share picks.")
            st.markdown(f"<div class='purposeExplain' style='background:{style['background']};color:{style['colour']}'>"
                        f"<b>{style['icon']} {style['label']}</b><br>{explanation}</div>", unsafe_allow_html=True)
        problem = None if form["purpose"] else "Please choose who the money is for."
        if form["purpose"] == "Both":
            form["legacyShare"] = radioChoice("How much is for the legacy?", {
                "A quarter": 0.25, "Half": 0.5, "Three quarters": 0.75}, form["legacyShare"], horizontal=True)
            if form["legacyShare"] is None:
                problem = "Please choose how much is for the legacy."
        else:
            form["legacyShare"] = 0.0
        stepButtons(problem)

    elif signupStep == 2:
        pageHeader("🎯 Your money and your goal",
                   "How much would you like to invest, what would you like it to grow to, and by when?", "step2")
        form["totalAmount"] = st.number_input("How much would you like to invest? ($)", min_value=1_000,
                                              max_value=10_000_000, value=form["totalAmount"], step=1_000,
                                              placeholder="e.g. 100000")
        form["goalAmount"] = st.number_input("What would you like it to grow to? ($)", min_value=1_000,
                                             max_value=50_000_000, value=form["goalAmount"], step=1_000,
                                             placeholder="e.g. 150000")
        form["goalYears"] = radioChoice("By when?", {f"{years} years": years for years in (3, 5, 10, 15, 20)},
                                        form["goalYears"], horizontal=True)
        problem = None
        if not (form["totalAmount"] and form["goalAmount"] and form["goalYears"]):
            problem = "Please answer all three questions."
        elif form["goalAmount"] <= form["totalAmount"]:
            problem = "Your goal should be more than the amount you invest."
        else:
            neededReturn = (form["goalAmount"] / form["totalAmount"]) ** (1 / form["goalYears"]) - 1
            st.info(f"To get there you'd need about **{neededReturn:.1%} growth a year**. "
                    + ("That's realistic for a balanced plan." if neededReturn <= 0.06 else
                       "That's ambitious. We'll show you your chances honestly."))
        stepButtons(problem)

    elif signupStep == 3:
        pageHeader("🌦️ You and risk", "Three questions about how you feel when the value of your money goes up "
                                      "and down, your experience, and whether you want income or growth.", "step3")
        form["riskLevel"] = radioChoice(
            f"If your ${form['totalAmount']:,.0f} fell to ${form['totalAmount'] * 0.8:,.0f} for a few months, what would you do?",
            {"😟  Sell, I couldn't sleep": "low", "😐  Feel uneasy, but wait": "mid",
             "🙂  Stay calm, maybe even invest more": "high"}, form["riskLevel"])
        form["experience"] = radioChoice("Have you invested before?",
                                         {"Never": "Never", "A little": "A little", "Yes, often": "Yes, often"},
                                         form["experience"], horizontal=True)
        form["incomePreference"] = radioChoice(
            "What matters more to you?",
            {"💵  A regular income (dividends)": "income", "⚖️  A bit of both": "balanced",
             "📈  The most growth over time": "growth"}, form["incomePreference"])
        problem = None if form["riskLevel"] and form["experience"] and form["incomePreference"] \
            else "Please answer all three questions."
        stepButtons(problem)

    elif signupStep == 4:
        pageHeader("🚫 Anything to avoid?", "Are there any industries you'd rather not invest in? "
                                            "This is optional. Leave it empty if there's nothing.", "step4")
        form["avoidIndustries"] = st.multiselect(
            "Industries you'd rather not invest in (optional)", sorted(set(CANDIDATE_STOCKS.values())),
            default=form["avoidIndustries"], placeholder="Leave empty if there's nothing")
        stepButtons(None)

    elif signupStep == 5:
        pageHeader("🔔 Smart-time alerts", "Choose which emails you'd like: when it's a smart time to invest, "
                                          "when it may be time to take profit, and a weekly summary.", "step5")
        st.write(f"We'll watch the market for you and email **{form['email']}** when it's worth acting.")
        form["notifyBuy"] = st.checkbox("📈  Tell me when it's a smart time to invest "
                                        "(a good investment is cheaper than usual)", value=form["notifyBuy"])
        form["notifySell"] = st.checkbox("💰  Tell me when it may be time to take profit or rebalance",
                                         value=form["notifySell"])
        form["notifyWeekly"] = st.checkbox("📬  Send me a short weekly summary", value=form["notifyWeekly"])
        with st.expander("How do you decide it's a smart time?"):
            st.write("We compare today's price with its usual price over the last 200 days and how fast it has "
                     "moved recently (RSI). A strong company that has dipped below its usual price is a smart "
                     "time to invest. One that has shot up far above it may be a time to take some profit. "
                     "These are signals from past prices, not guarantees.")
        stepButtons(None, nextLabel="✨  Build my plan")

    else:
        st.session_state.page = "building"
        st.rerun()

# ---------------------------------------------------------------------------
# Build the plan straight after sign-up
# ---------------------------------------------------------------------------
elif page == "building":
    ui.sectionTitle("🌳 Building your plan")
    with st.status("Working on it...", expanded=True) as status:
        st.write("📊 Reading prices, company reports, analyst ratings and news...")
        snapshot = cachedSnapshot()
        fundStats = cachedFundStats()
        st.write("🧠 The AI is analysing key indicators, your age and your preferences...")
        newProfile = buildAdvice(InvestorAnswers(**form), snapshot, fundStats)
        st.write("🎯 Testing the plan against your goal in 2,000 possible futures...")
        newProfile["explanation"] = advisor.explainGoalPlan(newProfile)
        newProfile["settings"] = dict(settings)
        saveProfile(newProfile)
        status.update(label="Your plan is ready", state="complete")
    st.session_state.profile = newProfile
    st.session_state.page = "dashboard"
    st.rerun()

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
else:
    profile = st.session_state.profile
    answers = profile["answers"]
    projection = profile["projection"]
    snapshot = cachedSnapshot()
    priceHistory = cachedPrices()
    alerts = buildAlerts(profile, snapshot, brokerLink)
    updates = buildUpdates(profile, snapshot, alerts)
    purchases = profile.setdefault("purchases", {
        key: {"date": profile["createdOn"], "price": next((holding.get("priceAtPlan") for holding in profile["holdings"]
                                                           if holdingKeyFor(holding) == key), None)}
        for key in profile.get("boughtTickers", [])})
    valuedHoldings = holdingCurrentValues(profile["holdings"], snapshot, purchases)
    valueNow = sum(holding["currentValue"] for holding in valuedHoldings)
    investedAmount = sum(holding["amount"] for holding in valuedHoldings if holding["isInvested"])
    recordValue(profile, valueNow)
    hasBothPurposes = len(profile["purposeTotals"]) > 1

    goalYear = int(profile["createdOn"][:4]) + answers["goalYears"]
    urgentCount = sum(1 for alert in alerts if alert["type"] in ("buy", "sell", "rebalance", "watch"))
    ui.heroCard(answers["name"].split(" ")[0], valueNow, answers["totalAmount"], investedAmount,
                answers["goalAmount"], goalYear, projection["chanceOfReachingGoal"], urgentCount)

    homeTab, planTab, historyTab, askTab, alertsTab = st.tabs(["🏠 Home", "📊 Plan", "🕒 History", "💬 Ask", "🔔 Alerts"])

    # --- Home: what to invest in, when, how much ---------------------------------
    with homeTab:
        purposeTiles = [(PURPOSE_STYLES[purpose]["icon"], purpose, f"${amount / 1000:,.0f}k")
                        for purpose, amount in profile["purposeTotals"].items()]
        potTiles = [(POT_ICONS[pot], pot.split(" ")[0] if pot != POT_SHARES else "AI picks", f"${amount / 1000:,.0f}k")
                    for pot, amount in profile["potTotals"].items() if amount]
        ui.tilesCard("Your money", (purposeTiles + potTiles)[:3] + [("🔔", "Alerts", str(urgentCount))])

        ui.sectionTitle("What to do next")
        listenText = "Here is what to do next. " + " ".join(
            f"{update['when']}: {update['title']}. {update['message']}" for update in updates[:4])
        ui.speakButton(listenText, "homeSummary", speechRate, label="🔊 Read my next steps")

        purposeFilter = "All"
        if hasBothPurposes:
            purposeFilter = st.segmented_control(
                "Show", ["All", f"🏖️ {PURPOSE_RETIREMENT}", f"🎁 {PURPOSE_LEGACY}"], default="All") or "All"
        st.caption(f"Invest buttons open {brokerName()} in a new tab. Nothing is bought until you confirm there.")

        for index, update in enumerate(updates):
            holding = update.get("holding")
            if purposeFilter != "All" and (not holding or holding["purpose"] not in purposeFilter):
                continue
            with st.container(border=True):
                indicators = (snapshot["stocks"].get(update["ticker"], {}).get("yahooFinance")
                              or snapshot.get("funds", {}).get(update["ticker"], {})) if update.get("ticker") else {}
                if holding:
                    oneYear = indicators.get("oneYearReturn")
                    ui.dealCard(
                        title=holding["name"], subtitle=f"{holding['assetType']} · {holding['pot']}",
                        when=update["when"], purpose=holding["purpose"],
                        columns=[("Amount", f"${update['amount']:,.0f}"),
                                 ("Yield", f"{indicators['dividendYield']:.1%}" if indicators.get("dividendYield") else "–"),
                                 ("Growth / yr", f"{indicators['fiveYearAnnualReturn']:.1%}"
                                  if indicators.get("fiveYearAnnualReturn") is not None else "–")],
                        segmentsOn=ui.steadinessSegments(indicators.get("annualVolatility")),
                        footLeft=f"Last 1y {oneYear:+.0%}" if oneYear is not None else "Steadiness",
                        pill=holding["ticker"], footRight=f"Data {snapshot.get('builtOn', '')[5:]}",
                        message=update["message"])
                else:
                    ui.dealCard(title=update["title"], subtitle=update.get("ticker") or "Your plan",
                                when=update["when"], columns=[], segmentsOn=0, footLeft="", pill="",
                                footRight="", message=update["message"])

                if update.get("link"):
                    amountText = f" ${update['amount']:,.0f}" if update.get("amount") else ""
                    st.link_button(f"{update['buttonWord']}{amountText} on {brokerName()} ↗", update["link"],
                                   type="primary" if update["when"] != "Wait" else "secondary",
                                   use_container_width=True)
                actionColumns = st.columns(2)
                with actionColumns[0]:
                    ui.speakButton(f"{update['title']}. {update['message']}", f"card{index}", speechRate)
                if update.get("holdingKey") and actionColumns[1].button("✓ I've done this", key=f"done{index}",
                                                                        use_container_width=True):
                    profile["boughtTickers"] = sorted(set(profile["boughtTickers"]) | {update["holdingKey"]})
                    # Growth counts from today's price, the day it was actually bought.
                    profile["purchases"][update["holdingKey"]] = {
                        "date": pd.Timestamp.today().date().isoformat(),
                        "price": latestPriceFor(snapshot, holding["ticker"])}
                    logEvent(profile, "✅", f"Invested ${update['amount']:,.0f} in {holding['name']}",
                             f"{PURPOSE_STYLES[holding['purpose']]['icon']} {holding['purpose']} · {holding['ticker']}")
                    st.rerun()
                if update.get("ticker"):
                    with st.expander("📊 Why this one?"):
                        whyThisOne(update["ticker"], (holding or {}).get("reason", ""), snapshot, priceHistory)

        doneHoldings = [holding for holding in profile["holdings"] if holdingKeyFor(holding) in profile["boughtTickers"]]
        if doneHoldings:
            with st.expander(f"✅ Already invested ({len(doneHoldings)})"):
                for holding in doneHoldings:
                    st.write(f"{PURPOSE_STYLES[holding['purpose']]['icon']} {holding['name']} "
                             f"({holding['ticker']}): ${holding['amount']:,.0f}")

    # --- Plan: pie charts, path to goal, explanations ------------------------------
    with planTab:
        ui.sectionTitle("What you've invested in")
        holdingsFrame = pd.DataFrame(profile["holdings"])
        assetFrame = holdingsFrame.groupby("assetType", as_index=False)["amount"].sum().rename(
            columns={"assetType": "Type", "amount": "Amount"}).sort_values("Amount", ascending=False)
        donutChart(assetFrame, "Type", ASSET_COLOURS)
        ui.speakButton("You have invested in: " + ", ".join(
            f"{row.Type}, {row.Amount:,.0f} dollars" for row in assetFrame.itertuples()), "assetPie", speechRate)
        for row in assetFrame.itertuples():
            with st.expander(f"{row.Type}: ${row.Amount:,.0f}"):
                st.write(ASSET_TYPE_EXPLANATIONS.get(row.Type, ""))
                typeHoldings = holdingsFrame[holdingsFrame["assetType"] == row.Type]
                st.dataframe(pd.DataFrame({
                    "For": typeHoldings["purpose"].map(lambda purpose: f"{PURPOSE_STYLES[purpose]['icon']} {purpose}"),
                    "Investment": typeHoldings["name"], "Code": typeHoldings["ticker"],
                    "Amount": typeHoldings["amount"].map(lambda amount: f"${amount:,.0f}")}),
                    hide_index=True, use_container_width=True)

        if hasBothPurposes:
            ui.sectionTitle("Retirement and legacy")
            purposeFrame = pd.DataFrame([{"Purpose": f"{PURPOSE_STYLES[purpose]['icon']} {purpose}", "Amount": amount}
                                         for purpose, amount in profile["purposeTotals"].items()])
            donutChart(purposeFrame, "Purpose", {f"{PURPOSE_STYLES[PURPOSE_RETIREMENT]['icon']} {PURPOSE_RETIREMENT}": "#2B5797",
                                                 f"{PURPOSE_STYLES[PURPOSE_LEGACY]['icon']} {PURPOSE_LEGACY}": "#7A3E9D"},
                       height=240)
        for purpose, amount in profile["purposeTotals"].items():
            style = PURPOSE_STYLES[purpose]
            with st.expander(f"{style['icon']} {style['label']}: ${amount:,.0f}"):
                for pot in (POT_SAFETY, POT_CORE, POT_SHARES):
                    potHoldings = [holding for holding in profile["holdings"]
                                   if holding["purpose"] == purpose and holding["pot"] == pot]
                    if potHoldings:
                        st.markdown(f"**{POT_ICONS[pot]} {pot}**: {POT_ROLES[pot]}")
                        st.markdown("\n".join(f"- {holding['name']} ({holding['ticker']}): ${holding['amount']:,.0f}"
                                              for holding in potHoldings))

        ui.sectionTitle("Your path to the goal")
        bands = pd.DataFrame(projection["bands"])
        bandArea = alt.Chart(bands).mark_area(opacity=0.18, color="#7FD33F").encode(
            x=alt.X("year:Q", title="Years from now"),
            y=alt.Y("bad (1 in 10):Q", title="Value ($)", axis=alt.Axis(format="$,.0f")), y2="good (1 in 10):Q")
        typicalLine = alt.Chart(bands).mark_line(strokeWidth=4, color=ui.DEEP_GREEN).encode(
            x="year:Q", y="typical:Q",
            tooltip=[alt.Tooltip("year:Q", title="Year"), alt.Tooltip("typical:Q", format="$,.0f", title="Typical"),
                     alt.Tooltip("bad (1 in 10):Q", format="$,.0f", title="Bad case")])
        goalLine = alt.Chart(pd.DataFrame({"goal": [answers["goalAmount"]]})).mark_rule(
            strokeDash=[8, 4], color="#E08E2B", strokeWidth=2).encode(y="goal:Q")
        st.altair_chart((bandArea + typicalLine + goalLine).properties(height=300), use_container_width=True)
        st.caption("Green line: a typical future. Shaded: from a bad run (1 in 10) to a good one. Orange dashes: your goal.")

        with st.expander("🧠 How the AI built your plan"):
            st.markdown(profile["explanation"])
            ui.speakButton(profile["explanation"], "planExplanation", speechRate)
        with st.expander("🔍 The key indicators the AI checks"):
            st.markdown("- **Steadiness:** how much the price swings and its worst fall (Yahoo Finance)\n"
                        "- **Income:** dividend paid each year (Yahoo Finance)\n"
                        "- **Quality:** profit margin and revenue growth (SEC EDGAR annual reports), debt (Finnhub)\n"
                        "- **Value:** price compared with earnings, the P/E ratio (Finnhub)\n"
                        "- **Experts:** share of analysts rating it a buy (Finnhub)\n"
                        "- **Timing:** price vs its 200-day average and recent speed, RSI (Yahoo Finance)\n"
                        "- **Your age:** retirement money keeps more in the safety cushion as you get older\n"
                        "- **The economy:** interest rates and inflation (FRED)")
            if profile.get("stockSummary"):
                st.info(profile["stockSummary"])
        if profile["stockAdjustments"]:
            with st.expander("🛡️ How we double-checked the AI"):
                st.markdown("\n".join(f"- {adjustment}" for adjustment in profile["stockAdjustments"]))
        if profile["stockSkipped"]:
            with st.expander("🙅 Companies the AI decided against"):
                st.markdown("\n".join(f"- **{skipped.get('ticker')}**: {skipped.get('reason')}"
                                      for skipped in profile["stockSkipped"]))
        with st.expander("📚 Where our data comes from"):
            st.markdown("- [Yahoo Finance](https://finance.yahoo.com): 5 years of daily prices and dividends\n"
                        "- [Finnhub](https://finnhub.io): analyst ratings, valuation and company news\n"
                        "- [SEC EDGAR](https://www.sec.gov/edgar/search/): companies' official annual reports\n"
                        "- [FRED, US Federal Reserve](https://fred.stlouisfed.org): interest rates and inflation\n\n"
                        f"Market data from {snapshot.get('builtOn', 'today')}. {profile['stockSource']}.")

    # --- History ---------------------------------------------------------------------
    with historyTab:
        ui.sectionTitle("Your money over time")
        valueHistory = pd.DataFrame(profile.get("valueHistory", []))
        if len(valueHistory) >= 2:
            valueHistory["date"] = pd.to_datetime(valueHistory["date"])
            st.altair_chart(alt.Chart(valueHistory).mark_line(strokeWidth=4, color=ui.DEEP_GREEN, point=True).encode(
                x=alt.X("date:T", title=None), y=alt.Y("value:Q", title="Value ($)", scale=alt.Scale(zero=False),
                                                       axis=alt.Axis(format="$,.0f")),
                tooltip=[alt.Tooltip("date:T"), alt.Tooltip("value:Q", format="$,.0f")]).properties(height=240),
                use_container_width=True)
        else:
            st.info(f"We save your balance each day you visit. Come back tomorrow to see your line grow. "
                    f"Today: ${valueNow:,.0f}.")

        ui.sectionTitle("How this plan did over the past year")
        backtest = backtestPlan(profile["holdings"], priceHistory)
        if not backtest.empty:
            endValue = backtest["Value"].iloc[-1]
            changeShare = endValue / answers["totalAmount"] - 1
            backtestChart = alt.Chart(backtest).mark_area(
                line={"color": ui.DEEP_GREEN, "strokeWidth": 3}, opacity=0.25,
                color=alt.Gradient(gradient="linear", stops=[alt.GradientStop(color="white", offset=0),
                                                             alt.GradientStop(color="#7FD33F", offset=1)],
                                   x1=1, x2=1, y1=1, y2=0)).encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Value:Q", title="Value ($)", scale=alt.Scale(zero=False), axis=alt.Axis(format="$,.0f")),
                tooltip=[alt.Tooltip("Date:T"), alt.Tooltip("Value:Q", format="$,.0f")])
            startRule = alt.Chart(pd.DataFrame({"start": [answers["totalAmount"]]})).mark_rule(
                strokeDash=[6, 4], color="#999").encode(y="start:Q")
            st.altair_chart((backtestChart + startRule).properties(height=240), use_container_width=True)
            backtestSentence = (f"If you had started this plan a year ago, your ${answers['totalAmount']:,.0f} "
                                f"would now be about ${endValue:,.0f} ({changeShare:+.1%}).")
            st.write(backtestSentence)
            st.caption("Uses real daily prices from Yahoo Finance. Past results don't guarantee future ones.")
            ui.speakButton(backtestSentence, "backtest", speechRate)
        else:
            st.info("Run `python stock_data.py` to download price history for this chart.")

        ui.sectionTitle("Activity")
        ui.timeline(profile.get("history", []))

    # --- Ask AI -------------------------------------------------------------------------
    with askTab:
        ui.sectionTitle("💬 Ask anything")
        st.caption(f"Simple answers from {advisor.chatModelName}, based on your plan.")
        planContext = json.dumps({
            "investor": answers, "valueToday": round(valueNow), "potTotals": profile["potTotals"],
            "moneyByPurpose": profile["purposeTotals"],
            "holdings": [{key: holding[key] for key in ("purpose", "pot", "assetType", "name", "ticker", "amount")}
                         for holding in profile["holdings"]],
            "projection": {key: value for key, value in projection.items() if key != "bands"},
            "nextSteps": [f"{update['when']}: {update['title']}" for update in updates],
            "economy": snapshot["economy"],
        }, default=str)
        suggestions = ["Why this plan?", "Is now a good time to invest?", "What's a bond?"]
        pendingQuestion = None
        for column, suggestion in zip(st.columns(len(suggestions)), suggestions):
            if column.button(suggestion, use_container_width=True):
                pendingQuestion = suggestion
        chatHistory = st.session_state.chatHistory
        for messageIndex, message in enumerate(chatHistory):
            with st.chat_message(message["role"], avatar="🙂" if message["role"] == "user" else "🌳"):
                st.markdown(message["content"])
                if message["role"] == "assistant":
                    ui.speakButton(message["content"], f"chat{messageIndex}", speechRate)
        question = st.chat_input("Type your question...") or pendingQuestion
        if question:
            chatHistory.append({"role": "user", "content": question})
            with st.spinner("Thinking..."):
                replyText = advisor.chatReply(chatHistory, planContext)
            chatHistory.append({"role": "assistant", "content": replyText})
            st.rerun()

    # --- Alerts & settings -------------------------------------------------------------
    with alertsTab:
        ui.sectionTitle("🔔 Your alerts")
        st.caption(f"Sent to {answers['email']}")
        notificationChoices = {"notifyBuy": "📈 Smart time to invest",
                               "notifySell": "💰 Time to take profit or rebalance",
                               "notifyWeekly": "📬 Weekly summary"}
        for settingKey, settingLabel in notificationChoices.items():
            newValue = st.toggle(settingLabel, value=answers.get(settingKey, False))
            if newValue != answers.get(settingKey, False):
                answers[settingKey] = newValue
                logEvent(profile, "🔔", f"{settingLabel} turned {'on' if newValue else 'off'}")
                st.success("Saved.")

        wantedTypes = ({"buy", "watch"} if answers.get("notifyBuy") else set()) | \
                      ({"sell", "rebalance"} if answers.get("notifySell") else set())
        chosenAlerts = [alert for alert in alerts if alert["type"] in wantedTypes]
        if st.button("📧  Send me today's alerts now", type="primary", use_container_width=True):
            digest = buildWeeklyDigest(profile, snapshot, chosenAlerts)
            addToInbox(profile, digest)
            succeeded, message = sendEmail(answers["email"], digest["subject"], digestAsHtml(digest),
                                           digestAsText(digest))
            logEvent(profile, "📧", "Alerts sent" if succeeded else "Alerts saved to inbox",
                     f"{len(chosenAlerts)} alert{'s' if len(chosenAlerts) != 1 else ''}")
            (st.success if succeeded else st.warning)(message if succeeded else message + " It's in your inbox below.")
        if not emailIsConfigured():
            st.caption("Email isn't set up yet, so alerts arrive in the inbox below.")
        if profile.get("inbox"):
            ui.sectionTitle("📥 Inbox")
            for savedDigest in profile["inbox"]:
                with st.expander(f"{savedDigest['date']} · {savedDigest['subject']}"):
                    st.markdown(digestAsHtml(savedDigest), unsafe_allow_html=True)

        ui.sectionTitle("♿ Easier to use")
        newRate = st.radio("Reading-aloud speed", list(ui.SPEECH_RATES),
                           index=list(ui.SPEECH_RATES).index(settings["speechRate"]), horizontal=True)
        if newRate != settings["speechRate"]:
            settings["speechRate"] = newRate
            saveSettings()
            st.rerun()
        st.caption("Text size and high contrast are at the top of every screen. Every card has a 🔊 Listen button.")

        st.divider()
        editColumn, logoutColumn = st.columns(2)
        if editColumn.button("✏️  Change my answers", use_container_width=True):
            st.session_state.form = {key: answers.get(key, EMPTY_FORM[key]) for key in EMPTY_FORM}
            st.session_state.signupStep = 0
            st.session_state.page = "signup"
            st.rerun()
        if logoutColumn.button("👋  Log out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.markdown("<p class='disclaimer'>Educational hackathon project. Not financial advice. "
                "Past performance doesn't guarantee future results.</p>", unsafe_allow_html=True)
