# 🌳 Heirloom

An AI investment analyst for a $100,000 investment. You sign up with your goal (for example, grow $100k to $150k in 10 years), and Heirloom tells you **what to invest in, how much, and when**. It explains why with charts and public sources, emails you when it's a smart time to act, and answers questions in a chat box powered by GPT-6 Astra.

*Educational hackathon project. Not financial advice.*

## Run it (Mac)

```zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your keys
python stock_data.py        # collect today's market data (good Wi-Fi!)
python prefetch.py          # cache crash-replay data
streamlit run app.py
```

## The app

| Screen | What it does |
|---|---|
| **Sign up** (6 screens, nothing pre-filled) | Name, email, age → who it's for (🏖️ retirement, 🎁 legacy, or both) → amount, goal, timeframe → risk, experience, income or growth → industries to avoid → smart-time alerts |
| **🏠 Home** | Balance card, money tiles, and a to-do feed. Each card has a purpose badge, a when label, an Invest button, 🔊 Listen, ✓ Done, and a **Why this one?** drop-down |
| **📊 Plan** | Pie chart of what you own (cash, government bonds, bonds, world shares, dividend shares, company shares), a retirement-vs-legacy pie, the path-to-goal chart, and explanation drop-downs |
| **🕒 History** | Your balance over time, how the plan did over the past year (real prices), and an activity timeline |
| **💬 Ask** | GPT-6 Astra chat, with every answer readable aloud |
| **🔔 Alerts** | Alert choices, send now, inbox, reading speed, change answers |

**Accessibility:** a text size control (A / A+ / A++) and a high-contrast switch at the top of every screen. A 🔊 button reads each screen, card, chart summary and chat answer aloud, at a slow, normal or fast speed. Big tap targets throughout, and nothing is pre-filled.

**Retirement vs legacy:** retirement money keeps more safe as you get older (age 70 means at least 40% in the safety cushion), with a steadier core. Legacy money has a small cushion and gets the AI share picks, because it has the most time to grow. Every investment is labelled with its purpose.

## How the AI decides

1. **Data** (`stock_data.py`): Yahoo Finance prices and dividends, Finnhub analyst ratings, P/E, debt and news, SEC EDGAR revenue and profit, FRED rates and inflation.
2. **Key indicators**: volatility, worst fall, dividend yield, 5-year growth, analyst buy share, profit margin, P/E, debt-to-equity, RSI and distance from the 200-day average.
3. **Preferences**: avoided industries are removed first, and an income or growth preference changes the score weights.
4. **Steadiness score** (`stock_advisor.py`): ranks every company, so the AI starts from something objective.
5. **GPT-6.1 Sol** reads the indicators and news, then picks shares and amounts with a reason for each.
6. **Safety check**: limits per company and per industry, only approved companies, amounts add up exactly.


## Alerts (`signals.py`)

| Alert | Rule |
|---|---|
| 🟢 Good moment to add | Price at least 5% below its 200-day average **and** RSI ≤ 35 |
| 🟠 Take some profit | Price at least 15% above its 200-day average **and** RSI ≥ 72 (only if it's above plan) |
| 🟡 Wait | Price more than 15% below its average and still falling |
| ⚖️ Rebalance | An investment has drifted 5+ points from its planned share |
| 👀 On sale | A suitable share they don't own triggers the buy rule |

These are signals from past prices, not promises. Rebalancing is the best-evidenced "buy low, sell high" habit, which is why it's included.

## Weekly emails

- `python weekly_digest.py` sends the weekly update to everyone who opted in.
- `python weekly_digest.py --alerts` emails only people with buy, sell or rebalance alerts.
- `.github/workflows/notifications.yml` runs it every Monday, with alert checks Tuesday to Friday. Add your keys under GitHub → Settings → Secrets.
- Gmail: turn on 2-step verification, create an App password, and put it in `SMTP_PASSWORD`.

## Buy buttons

The buttons open `BROKER_URL_TEMPLATE` with the fund code filled in. It defaults to the Yahoo Finance quote page. Change it in `.env` to the investment platform you want to demo. Heirloom never buys anything itself: the client confirms on the platform.

## Known simplifications (say these if judges ask)

- Profiles are JSON files in `data/users/`. A real app would use a database and proper log-in.
- The 20-year projection models shares like the world fund. Returns are treated as normally distributed.
- Price signals use daily closing prices and can be wrong.

## 3-minute demo

1. **Sign up live as Maria** (50s): $100,000, goal $150,000 in 10 years, "feel uneasy but wait", avoid Energy, turn on all alerts.
2. **Updates** (50s): Coca-Cola shows "Good moment". Open **Why this one?** to see the chart, report card, news and sources. Tap Invest.
3. **My plan** (30s): the path-to-goal chart, "63% chance of reaching your goal", and how the AI was double-checked.
4. **Ask AI** (20s): "Is now a good time to invest?"
5. **Alerts** (20s): "Send me today's alerts now", so an email arrives on a phone.
6. **Close** (10s): *"Most AI tools ask you to trust them. Heirloom shows its working."*
