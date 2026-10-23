"""
ui.py — the look of Heirloom: deep green balance card, lime accents,
rounded white cards, and a pill-shaped navigation bar.

Everything visual lives here so app.py stays about behaviour.
"""

from datetime import datetime
from html import escape

import streamlit as st

DEEP_GREEN = "#0B5D3B"
DARK_GREEN = "#06402A"
LIME = "#B8F35A"
MINT = "#E8F5EE"
INK = "#10241B"
MUTED = "#6B7C74"

CHART_COLOURS = {"main": DEEP_GREEN, "accent": "#7FD33F", "soft": "#BFE6CF", "warn": "#E08E2B"}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stMarkdown, p, li, label, input, textarea, button {{
    font-family: 'Inter', sans-serif !important; color: {INK}; }}
.stMarkdown p, li, label {{ font-size: 18px !important; line-height: 1.5; }}
[data-testid="stAppViewContainer"] {{ background: linear-gradient(180deg, {MINT} 0%, #F6FBF8 100%); }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 520px; padding-top: 1.2rem; padding-bottom: 7rem; }}
h1, h2, h3 {{ font-weight: 800 !important; letter-spacing: -0.02em; color: {INK}; }}

/* Buttons: lime pill for primary, soft outline for the rest */
button[kind="primary"], [data-testid="stBaseButton-primary"],
a[kind="primary"], [data-testid="stBaseLinkButton-primary"] {{
    background: {LIME} !important; color: {INK} !important; border: none !important;
    border-radius: 999px !important; font-weight: 700 !important; min-height: 3rem; }}
button[kind="secondary"], [data-testid="stBaseButton-secondary"],
a[kind="secondary"], [data-testid="stBaseLinkButton-secondary"] {{
    background: white !important; color: {DEEP_GREEN} !important; border: 1.5px solid #D5E6DC !important;
    border-radius: 999px !important; font-weight: 600 !important; min-height: 3rem; }}
button p, a p {{ font-size: 17px !important; }}

/* Cards */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
    background: white; border: 1px solid #E3EEE8 !important; border-radius: 26px !important;
    box-shadow: 0 6px 24px rgba(11, 93, 59, 0.07); padding: 0.4rem 0.3rem; }}
[data-testid="stExpander"] details {{ border-radius: 18px !important; border: 1px solid #E3EEE8 !important;
    background: #FAFDFB; }}
[data-testid="stExpander"] summary p {{ font-weight: 600; }}

/* Inputs */
input, textarea, [data-baseweb="select"] > div {{ border-radius: 14px !important; }}
[data-testid="stProgress"] > div > div > div > div {{ background-color: {LIME} !important; }}

/* Pill navigation bar fixed at the bottom, like a mobile app */
[data-baseweb="tab-list"] {{
    position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); z-index: 1000;
    background: linear-gradient(135deg, {DEEP_GREEN}, {DARK_GREEN}); border-radius: 999px;
    padding: 8px 10px; gap: 4px; box-shadow: 0 10px 30px rgba(6, 64, 42, 0.35); width: min(480px, 92vw);
    justify-content: space-between; }}
[data-baseweb="tab"] {{ background: transparent !important; border-radius: 999px !important;
    padding: 10px 14px !important; height: auto !important; }}
[data-baseweb="tab"] p {{ color: #CFE9DB !important; font-size: 15px !important; font-weight: 600; }}
[data-baseweb="tab"][aria-selected="true"] {{ background: {LIME} !important; }}
[data-baseweb="tab"][aria-selected="true"] p {{ color: {INK} !important; }}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{ display: none; }}

/* Hero balance card */
.hero {{ background: radial-gradient(circle at 85% 0%, #1E7A52 0%, {DEEP_GREEN} 45%, {DARK_GREEN} 100%);
    border-radius: 30px; padding: 22px 22px 20px; color: white; margin-bottom: 14px;
    box-shadow: 0 14px 34px rgba(6, 64, 42, 0.30); }}
.heroTop {{ display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }}
.heroAvatar {{ width: 44px; height: 44px; border-radius: 14px; background: rgba(184, 243, 90, 0.18);
    display: flex; align-items: center; justify-content: center; font-size: 22px; }}
.heroGreeting {{ font-size: 13px; color: #BFE6CF; }}
.heroName {{ font-size: 17px; font-weight: 700; }}
.heroIcons {{ margin-left: auto; display: flex; gap: 8px; }}
.heroIcon {{ width: 38px; height: 38px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.25);
    display: flex; align-items: center; justify-content: center; font-size: 16px; position: relative; }}
.heroDot {{ position: absolute; top: 6px; right: 7px; width: 8px; height: 8px; border-radius: 50%; background: {LIME}; }}
.heroLabel {{ font-size: 14px; color: #BFE6CF; }}
.heroValue {{ font-size: 38px; font-weight: 800; letter-spacing: -0.03em; display: flex; align-items: center; gap: 12px; }}
.heroChip {{ font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.3); }}
.heroChange {{ font-size: 14px; color: {LIME}; margin-top: 2px; }}
.heroInvested {{ margin-top: 16px; }}
.heroInvestedText {{ display: flex; justify-content: space-between; font-size: 13px; color: #BFE6CF; margin-bottom: 6px; }}
.heroInvestedText b {{ color: white; font-size: 14px; }}
.heroBar {{ height: 10px; border-radius: 999px; background: rgba(255,255,255,0.15); overflow: hidden; }}
.heroBar div {{ height: 100%; border-radius: 999px; background: {LIME}; }}
.heroStats {{ display: flex; gap: 10px; margin-top: 18px; }}
.heroStat {{ flex: 1; background: rgba(255,255,255,0.08); border-radius: 16px; padding: 10px 12px; }}
.heroStat span {{ display: block; font-size: 12px; color: #BFE6CF; }}
.heroStat b {{ font-size: 17px; }}

/* Category-style tiles */
.tileCard {{ background: white; border-radius: 26px; padding: 18px; margin-bottom: 16px;
    box-shadow: 0 6px 24px rgba(11, 93, 59, 0.07); border: 1px solid #E3EEE8; }}
.tileCardTitle {{ font-weight: 800; font-size: 18px; margin-bottom: 14px; }}
.tileGrid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; text-align: center; }}
.tileCircle {{ width: 54px; height: 54px; margin: 0 auto 6px; border-radius: 50%; background: {MINT};
    display: flex; align-items: center; justify-content: center; font-size: 22px; }}
.tileLabel {{ font-size: 12px; color: {MUTED}; }}
.tileValue {{ font-size: 14px; font-weight: 700; }}

/* Deal cards (each update) */
.dealHead {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
.dealTitle {{ font-size: 19px; font-weight: 800; line-height: 1.25; }}
.dealSub {{ font-size: 13px; color: {MUTED}; margin-top: 2px; }}
.dealBadge {{ flex-shrink: 0; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 700; }}
.dealGrid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 14px 0 12px; }}
.dealGrid span {{ display: block; font-size: 12px; color: {MUTED}; }}
.dealGrid b {{ font-size: 16px; }}
.segments {{ display: flex; gap: 4px; margin-bottom: 10px; }}
.segments i {{ flex: 1; height: 9px; border-radius: 6px; background: #D9DED9; }}
.segments i.on {{ background: #9BE15D; }}
.dealFoot {{ display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: {MUTED}; }}
.dealPill {{ background: {INK}; color: white; padding: 3px 10px; border-radius: 999px; font-weight: 600; }}
.dealMessage {{ font-size: 15px !important; color: #3D5248; margin: 10px 0 4px; }}

/* Welcome banner */
.banner {{ background: radial-gradient(circle at 80% 20%, #2C8A5F 0%, {DEEP_GREEN} 40%, #052E1F 100%);
    border-radius: 30px; padding: 34px 26px; color: white; margin: 8px 0 18px; }}
.banner h1 {{ color: white !important; font-size: 34px !important; line-height: 1.15; margin: 0 0 10px; }}
.banner p {{ color: #CFE9DB; font-size: 16px !important; margin: 0; }}
.bannerTag {{ display: inline-block; font-size: 12px; font-weight: 700; letter-spacing: 0.08em;
    color: {INK}; background: {LIME}; padding: 4px 10px; border-radius: 999px; margin-bottom: 14px; }}
.sectionTitle {{ font-size: 20px; font-weight: 800; margin: 18px 0 10px; }}
.disclaimer {{ font-size: 13px !important; color: #8A9A92; text-align: center; }}
.purposeBadge {{ display: inline-block; font-size: 13px; font-weight: 700; padding: 4px 12px;
    border-radius: 999px; margin-bottom: 10px; }}
.timelineRow {{ display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid #E8EFEB; }}
.timelineIcon {{ width: 40px; height: 40px; flex-shrink: 0; border-radius: 50%; background: {MINT};
    display: flex; align-items: center; justify-content: center; font-size: 18px; }}
.timelineText {{ font-weight: 700; font-size: 16px; }}
.timelineDetail {{ font-size: 14px; color: {MUTED}; }}
.purposeExplain {{ border-radius: 20px; padding: 14px 16px; margin: 6px 0; font-size: 15px; }}
</style>
"""

WHEN_BADGES = {
    "Good moment": ("#E3F8D2", "#2E7D1F"), "Now": ("#E3F8D2", "#2E7D1F"),
    "In two halves": ("#FFF4D6", "#8A6A00"), "Wait": ("#FFF4D6", "#8A6A00"),
    "Take profit": ("#FFE8D6", "#A4520F"), "Rebalance": ("#E2ECFA", "#2B5797"),
    "Goal": ("#E2ECFA", "#2B5797"), "Every 6 months": ("#EEF0EE", "#55625B"),
}


def applyTheme():
    st.markdown(CSS, unsafe_allow_html=True)


def greeting() -> str:
    hour = datetime.now().hour
    return "Good morning!" if hour < 12 else "Good afternoon!" if hour < 18 else "Good evening!"


def heroCard(name: str, valueNow: float, startValue: float, investedAmount: float, goalAmount: float,
             goalYear: int, chance: float, alertCount: int):
    change = valueNow - startValue
    if investedAmount == 0:
        changeText = "Nothing invested yet. Start with the first card below."
    else:
        changeText = f"{'▲' if change >= 0 else '▼'} ${abs(change):,.2f} on what you've invested"
    investedShare = investedAmount / startValue if startValue else 0
    st.markdown(f"""
    <div class="hero">
      <div class="heroTop">
        <div class="heroAvatar">🌳</div>
        <div><div class="heroGreeting">{greeting()}</div><div class="heroName">{escape(name)}</div></div>
        <div class="heroIcons"><div class="heroIcon">🔔{'<span class="heroDot"></span>' if alertCount else ''}</div></div>
      </div>
      <div class="heroLabel">Total balance</div>
      <div class="heroValue">${valueNow:,.2f} <span class="heroChip">USD</span></div>
      <div class="heroChange">{changeText}</div>
      <div class="heroInvested">
        <div class="heroInvestedText"><span>Invested so far</span><b>${investedAmount:,.0f} of ${startValue:,.0f}</b></div>
        <div class="heroBar"><div style="width:{investedShare:.0%}"></div></div>
      </div>
      <div class="heroStats">
        <div class="heroStat"><span>Goal by {goalYear}</span><b>${goalAmount:,.0f}</b></div>
        <div class="heroStat"><span>Waiting to invest</span><b>${startValue - investedAmount:,.0f}</b></div>
        <div class="heroStat"><span>Chance</span><b>{chance:.0%}</b></div>
      </div>
    </div>""", unsafe_allow_html=True)


def tilesCard(title: str, tiles: list):
    """tiles: [(icon, label, value)] — shown four to a row like app categories."""
    tileHtml = "".join(f"<div><div class='tileCircle'>{icon}</div><div class='tileLabel'>{escape(label)}</div>"
                       f"<div class='tileValue'>{escape(value)}</div></div>" for icon, label, value in tiles)
    st.markdown(f"<div class='tileCard'><div class='tileCardTitle'>{escape(title)}</div>"
                f"<div class='tileGrid'>{tileHtml}</div></div>", unsafe_allow_html=True)


def sectionTitle(text: str):
    st.markdown(f"<div class='sectionTitle'>{escape(text)}</div>", unsafe_allow_html=True)


def steadinessSegments(annualVolatility) -> int:
    if annualVolatility is None:
        return 2
    return 3 if annualVolatility < 0.10 else 2 if annualVolatility < 0.22 else 1


def purposeBadge(purpose: str) -> str:
    from portfolio import PURPOSE_STYLES
    style = PURPOSE_STYLES.get(purpose)
    if not style:
        return ""
    return (f"<span class='purposeBadge' style='background:{style['background']};color:{style['colour']}'>"
            f"{style['icon']} {style['label']}</span>")


def dealCard(title: str, subtitle: str, when: str, columns: list, segmentsOn: int,
             footLeft: str, pill: str, footRight: str, message: str = "", purpose: str = ""):
    """The rounded investment card. columns: [(label, value)] x3."""
    background, colour = WHEN_BADGES.get(when, ("#EEF0EE", "#55625B"))
    gridHtml = "".join(f"<div><span>{escape(label)}</span><b>{escape(value)}</b></div>" for label, value in columns)
    segmentHtml = "".join(f"<i class='{'on' if i < segmentsOn else ''}'></i>" for i in range(3))
    st.markdown(f"""
      {purposeBadge(purpose)}
      <div class="dealHead">
        <div><div class="dealTitle">{escape(title)}</div><div class="dealSub">{escape(subtitle)}</div></div>
        <div class="dealBadge" style="background:{background};color:{colour}">{escape(when)}</div>
      </div>
      {f'<p class="dealMessage">{escape(message)}</p>' if message else ''}
      {f'<div class="dealGrid">{gridHtml}</div>' if columns else ''}
      {f'<div class="segments">{segmentHtml}</div>' if columns else ''}
      <div class="dealFoot"><span>{escape(footLeft)}</span>{f'<span class="dealPill">{escape(pill)}</span>' if pill else ''}<span>{escape(footRight)}</span></div>
    """, unsafe_allow_html=True)


def welcomeBanner():
    st.markdown("""
    <div class="banner">
      <div class="bannerTag">AI ANALYST</div>
      <h1>The smarter way to grow your money</h1>
      <p>Tell us your goal. Our AI reads prices, company reports, analyst ratings and news,
      then tells you what to invest in, how much, and when.</p>
    </div>""", unsafe_allow_html=True)


TEXT_SIZES = {"A": 1.0, "A+": 1.18, "A++": 1.36}
SPEECH_RATES = {"Slow": 0.75, "Normal": 0.95, "Fast": 1.15}


def applyAccessibility(textSize: str, highContrast: bool):
    """Bigger text scales the whole page (cards, charts, buttons) so nothing overlaps."""
    zoom = TEXT_SIZES.get(textSize, 1.0)
    contrastCss = """
      [data-testid="stAppViewContainer"] { background: #FFFFFF !important; }
      .stMarkdown p, li, label, .dealSub, .tileLabel, .dealFoot, .dealGrid span, .timelineDetail,
      [data-testid="stCaptionContainer"] { color: #000000 !important; }
      [data-testid="stVerticalBlockBorderWrapper"], .tileCard { border: 2px solid #000000 !important; }
      .segments i { background: #9AA39C; } .segments i.on { background: #2E7D1F; }
    """ if highContrast else ""
    st.markdown(f"<style>.block-container {{ zoom: {zoom}; }} {contrastCss}</style>", unsafe_allow_html=True)


def speakButton(text: str, key: str, rate: float = 0.95, label: str = "🔊 Listen"):
    """Reads text aloud with the browser's built-in voice (works offline, no key needed)."""
    import json as jsonModule
    import streamlit.components.v1 as components
    cleanText = jsonModule.dumps(text.replace("*", "").replace("#", "").replace("_", " "))
    components.html(f"""
      <button id="speak{key}" style="font: 600 16px Inter, sans-serif; padding: 11px 14px; width: 100%;
        border-radius: 999px; border: 1.5px solid #D5E6DC; background: white; color: {DEEP_GREEN}; cursor: pointer">
        {label}</button>
      <script>
        const button = document.getElementById("speak{key}");
        button.onclick = () => {{
          if (speechSynthesis.speaking) {{ speechSynthesis.cancel(); button.innerText = "{label}"; return; }}
          const speech = new SpeechSynthesisUtterance({cleanText});
          speech.rate = {rate}; speech.lang = "en-GB";
          speech.onend = () => button.innerText = "{label}";
          button.innerText = "⏹ Stop"; speechSynthesis.speak(speech);
        }};
      </script>""", height=54)


def timeline(events: list):
    rows = "".join(
        f"<div class='timelineRow'><div class='timelineIcon'>{event['icon']}</div><div>"
        f"<div class='timelineText'>{escape(event['text'])}</div>"
        f"<div class='timelineDetail'>{escape(event['date'])}{' · ' + escape(event['detail']) if event.get('detail') else ''}"
        f"</div></div></div>" for event in events)
    st.markdown(f"<div class='tileCard'>{rows}</div>", unsafe_allow_html=True)
