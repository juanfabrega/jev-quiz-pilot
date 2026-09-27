"""Client for Jev on OpenRouter's decisions endpoint (not the chat endpoint)."""
import os

import requests

API_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"


def decide(state, questions):
    """Send one request. All questions are answered in parallel and can't see each other."""
    r = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={"model": MODEL, "state": state, "questions": questions},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["answers"]
