"""
ai_client.py — one place that connects to the AI.

Works with both kinds of endpoint, set in .env:
  - OpenAI-style (default):  OPENAI_BASE_URL=https://.../v1
  - Azure OpenAI:            OPENAI_API_TYPE=azure, OPENAI_BASE_URL=https://<name>.openai.azure.com,
                             OPENAI_API_VERSION=2024-10-21 (model names = deployment names)
Run `python test_ai.py` to find the right settings automatically.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def makeClient(timeout=60):
    apiKey = os.getenv("OPENAI_API_KEY")
    if not apiKey or apiKey == "your-key-here":
        return None
    baseUrl = os.getenv("OPENAI_BASE_URL") or None
    if os.getenv("OPENAI_API_TYPE", "").lower() == "azure":
        from openai import AzureOpenAI
        return AzureOpenAI(api_key=apiKey, azure_endpoint=baseUrl,
                           api_version=os.getenv("OPENAI_API_VERSION", "2024-10-21"), timeout=timeout)
    from openai import OpenAI
    return OpenAI(api_key=apiKey, base_url=baseUrl, timeout=timeout)
