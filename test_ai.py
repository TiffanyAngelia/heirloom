"""
Finds working AI settings for the UO portal and saves them to .env.
Run:  python test_ai.py
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
apiKey = os.getenv("OPENAI_API_KEY")
givenUrl = (os.getenv("OPENAI_BASE_URL") or "").rstrip("/")
if not apiKey or not givenUrl:
    raise SystemExit("Add OPENAI_API_KEY and OPENAI_BASE_URL to .env first.")

rootUrl = re.sub(r"/(v1|openai/v1|openai|api|api/v1)$", "", givenUrl)
urlsToTry = list(dict.fromkeys([givenUrl, rootUrl, rootUrl + "/v1", rootUrl + "/openai/v1",
                                rootUrl + "/api", rootUrl + "/api/v1"]))
modelsToTry = ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna", "gpt-5.6-terra"]

from openai import AzureOpenAI, OpenAI

print("Looking for models the portal lists...")
for url in urlsToTry:
    try:
        listedModels = [model.id for model in OpenAI(api_key=apiKey, base_url=url, timeout=15).models.list()]
        print(f"  {url}/models lists: {', '.join(listedModels[:10])}")
        modelsToTry = list(dict.fromkeys(modelsToTry + listedModels))
    except Exception as error:
        print(f"  {url}/models: {type(error).__name__} {getattr(error, 'status_code', '')}")

workingSettings = {}
print("\nTrying a one-word chat with each address and model...")
for apiType in ("openai", "azure"):
    for url in urlsToTry if apiType == "openai" else [rootUrl]:
        for model in modelsToTry:
            try:
                if apiType == "azure":
                    client = AzureOpenAI(api_key=apiKey, azure_endpoint=url, api_version="2024-10-21", timeout=20)
                else:
                    client = OpenAI(api_key=apiKey, base_url=url, timeout=20)
                reply = client.chat.completions.create(model=model, messages=[{"role": "user", "content": "Say hi"}])
                print(f"  ✅ {apiType} | {url} | {model} -> {reply.choices[0].message.content[:40]!r}")
                workingSettings.setdefault((apiType, url), []).append(model)
            except Exception as error:
                print(f"  ❌ {apiType} | {url} | {model} -> {type(error).__name__} {getattr(error, 'status_code', '')}")
        if workingSettings:
            break
    if workingSettings:
        break

if not workingSettings:
    raise SystemExit("\nNothing worked. Copy this output and ask the organisers which URL and model names to use.")

(apiType, url), workingModels = next(iter(workingSettings.items()))
preferred = lambda names: next((name for name in names if name in workingModels), workingModels[0])
newValues = {
    "OPENAI_BASE_URL": url,
    "OPENAI_API_TYPE": apiType,
    "MODEL_NAME": preferred(["gpt-6.1-sol", "gpt-6-astra"]),
    "QUICK_MODEL_NAME": preferred(["gpt-6-luna", "gpt-6.1-sol"]),
    "CHAT_MODEL_NAME": preferred(["gpt-6-astra", "gpt-6.1-sol"]),
}
envPath = Path(".env")
envLines = envPath.read_text().splitlines()
for name, value in newValues.items():
    replaced = False
    for index, line in enumerate(envLines):
        if line.startswith(name + "="):
            envLines[index] = f"{name}={value}"
            replaced = True
    if not replaced:
        envLines.append(f"{name}={value}")
envPath.write_text("\n".join(envLines) + "\n")
print("\nSaved to .env:")
for name, value in newValues.items():
    print(f"  {name}={value}")
print("\nNow restart the app: Ctrl + C, then streamlit run app.py")
