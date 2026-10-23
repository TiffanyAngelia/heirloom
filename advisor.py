"""
advisor.py — the AI's voice.

- explainGoalPlan: GPT-6.1 Sol explains the plan in plain English
- chatReply:       GPT-6 Astra answers questions in the chat box
- askModel:        short helper used by the weekly update

Rules decide the numbers; the AI explains them and answers questions using only
the client's real data. Without an API key, every function falls back to a
simple template so the demo never breaks.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

modelName = os.getenv("MODEL_NAME", "gpt-6.1-sol")
quickModelName = os.getenv("QUICK_MODEL_NAME", "gpt-6-luna")
chatModelName = os.getenv("CHAT_MODEL_NAME", "gpt-6-astra")

GUIDE_PROMPT = """You are Heirloom, a patient and friendly investment guide for people
who are new to investing. This is an educational hackathon tool, not regulated advice.
- Short sentences, everyday words. Explain any financial term in brackets.
- Only use numbers given to you. Name the source when you quote one
  (Yahoo Finance, Finnhub, SEC EDGAR, FRED).
- Never promise returns. Say "typically" or "in most of our simulations"."""

CHAT_PROMPT = GUIDE_PROMPT + """
In the chat:
- Answer in at most 3 short sentences that a 10-year-old could follow.
- Use the person's own plan numbers when they help.
- If you don't know, or it needs a professional (tax, legal), say so kindly.
- Don't suggest buying or selling beyond what the plan and alerts already say."""


def getClient():
    apiKey = os.getenv("OPENAI_API_KEY")
    if not apiKey:
        return None
    from openai import OpenAI
    return OpenAI(api_key=apiKey, base_url=os.getenv("OPENAI_BASE_URL") or None, timeout=60)


def askModel(userMessage: str, useQuickModel=False, model=None):
    """One-off question. Returns None if the AI isn't connected or fails."""
    client = getClient()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=model or (quickModelName if useQuickModel else modelName),
            messages=[{"role": "system", "content": GUIDE_PROMPT}, {"role": "user", "content": userMessage}])
        return response.choices[0].message.content
    except Exception:
        return None


def explainGoalPlan(profile: dict) -> str:
    answers = profile["answers"]
    projection = profile["projection"]
    facts = {
        "investor": {key: answers.get(key) for key in ("age", "purpose", "totalAmount", "goalAmount", "goalYears",
                                                       "riskLevel", "incomePreference", "avoidIndustries")},
        "potTotals": profile["potTotals"],
        "moneyByPurpose": profile.get("purposeTotals"),
        "holdings": [{key: holding.get(key) for key in ("purpose", "pot", "name", "ticker", "amount")}
                     for holding in profile["holdings"]],
        "aiSharePickSummary": profile["stockSummary"],
        "projection": {key: round(value, 3) for key, value in projection.items() if key != "bands"},
    }
    aiAnswer = askModel(
        "Explain this investment plan in under 160 words. Start with one sentence on how the money is "
        "split between retirement and legacy (if both) and between safety, core funds and AI picks. Then 3 bullets, "
        "each starting 'Because...', linking the plan to their age, purpose, goal and answers. "
        "Then a line starting '**How sure are we?**' using the chance of reaching the goal.\n\n"
        f"PLAN:\n{json.dumps(facts, default=str)}")
    if aiAnswer:
        return aiAnswer
    potTotals = profile["potTotals"]
    return (f"We split your ${answers['totalAmount']:,.0f} three ways: "
            + ", ".join(f"**${amount:,.0f}** in {pot}" for pot, amount in potTotals.items()) + ".\n\n"
            f"- Because you're {answers.get('age')} and chose **{answers['riskLevel']}** risk, "
            f"{potTotals['Safety cushion'] / answers['totalAmount']:.0%} stays in the safety cushion. "
            "Retirement money gets more safety as you get older; legacy money has longer to grow.\n"
            f"- Because your goal is ${answers['goalAmount']:,.0f} in {answers['goalYears']} years, you need about "
            f"{projection['requiredReturn']:.1%} a year. This plan typically makes about "
            f"{projection['expectedReturn']:.1%} (Yahoo Finance, past 10 years).\n"
            "- Because no single company should be able to hurt you much, the AI share picks are spread "
            "over several industries.\n\n"
            f"**How sure are we?** You reached your goal in {projection['chanceOfReachingGoal']:.0%} "
            "of 2,000 simulated futures.")


def chatReply(chatHistory: list, planContext: str) -> str:
    """chatHistory: [{"role": "user"|"assistant", "content": "..."}]. Uses GPT-6 Astra."""
    client = getClient()
    if client is None:
        return "The AI isn't connected yet. Add the API key to the .env file, then ask again."
    messages = [{"role": "system", "content": CHAT_PROMPT + "\n\nTHEIR PLAN:\n" + planContext}]
    messages += chatHistory[-8:]  # the last few turns, so follow-up questions make sense
    try:
        response = client.chat.completions.create(model=chatModelName, messages=messages)
        return response.choices[0].message.content
    except Exception as error:
        return f"Sorry, I couldn't answer just now ({error}). Please try again in a moment."
