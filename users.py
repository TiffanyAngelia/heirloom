"""
users.py — saves each client's profile as a JSON file in data/users/.

Good enough for a hackathon demo. A real app would use a database and proper
log-in (Streamlit Cloud wipes local files when it restarts).
"""

import json
import re
from pathlib import Path

usersFolder = Path(__file__).parent / "data" / "users"
usersFolder.mkdir(parents=True, exist_ok=True)


def profilePath(email: str) -> Path:
    safeName = re.sub(r"[^a-z0-9]+", "-", email.strip().lower()).strip("-")
    return usersFolder / f"{safeName}.json"


def saveProfile(profile: dict):
    profilePath(profile["answers"]["email"]).write_text(json.dumps(profile, indent=1, default=str))


def loadProfile(email: str):
    path = profilePath(email)
    return json.loads(path.read_text()) if path.exists() else None


def listProfiles() -> list:
    return [json.loads(path.read_text()) for path in sorted(usersFolder.glob("*.json"))]


def addToInbox(profile: dict, message: dict, maxMessages=20):
    profile.setdefault("inbox", []).insert(0, message)
    profile["inbox"] = profile["inbox"][:maxMessages]
    saveProfile(profile)
