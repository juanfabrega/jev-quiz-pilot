"""Client for Jev's decisions API, direct from TypeSafe or through OpenRouter.

Both take the same request and return the same answers. Only the URL, key, and model name differ.
Both pin Jev 1.13 so runs are comparable across providers.
"""
import os
from typing import NamedTuple

import requests


class Provider(NamedTuple):
    name: str
    url: str
    key_env: str
    model: str


PROVIDERS = {
    "typesafe": Provider("TypeSafe", "https://api.typesafe.ai/v1/systemone", "TYPESAFE_API_KEY", "jev-1.13.0"),
    "openrouter": Provider("OpenRouter", "https://openrouter.ai/api/alpha/decisions", "OPENROUTER_API_KEY",
                           "typesafe/jev-1.13"),
}


def pick_provider(choice="auto"):
    """Return the provider to use. "auto" takes the first one with a key set, TypeSafe first.

    Raises ValueError with a readable message if the needed key is missing.
    """
    if choice != "auto":
        p = PROVIDERS[choice]
        if not os.environ.get(p.key_env):
            raise ValueError(f"--provider {choice} needs {p.key_env}. Put it in .env or export it.")
        return p
    for p in PROVIDERS.values():
        if os.environ.get(p.key_env):
            return p
    keys = " or ".join(p.key_env for p in PROVIDERS.values())
    raise ValueError(f"No API key found. Set {keys} in .env or export it. See .env.example.")


def decide(provider, state, questions):
    """Send one request. All questions are answered in parallel and can't see each other."""
    r = requests.post(
        provider.url,
        headers={
            "Authorization": f"Bearer {os.environ[provider.key_env]}",
            "Content-Type": "application/json",
        },
        json={"model": provider.model, "state": state, "questions": questions},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["answers"]
