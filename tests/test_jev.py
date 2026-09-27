import pytest

from jev_quiz_pilot.jev import PROVIDERS, pick_provider


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    for p in PROVIDERS.values():
        monkeypatch.delenv(p.key_env, raising=False)


def test_auto_uses_the_key_that_is_set(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    assert pick_provider().name == "OpenRouter"


def test_auto_prefers_typesafe_when_both_set(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    assert pick_provider().name == "TypeSafe"
    assert pick_provider("openrouter").name == "OpenRouter"


def test_missing_keys_explain_what_to_set(monkeypatch):
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY or OPENROUTER_API_KEY"):
        pick_provider()
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    with pytest.raises(ValueError, match="needs TYPESAFE_API_KEY"):
        pick_provider("typesafe")
