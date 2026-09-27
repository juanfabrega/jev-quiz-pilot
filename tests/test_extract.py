"""Smoke test for extract.js: load a local quiz page in headless Chromium and check what it finds.

Needs no API key. Needs Chromium: uv run playwright install chromium
"""
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from jev_quiz_pilot.runner import EXTRACT_JS

QUIZ = (Path(__file__).parent / "quiz.html").as_uri()


@pytest.fixture(scope="module")
def fields():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(QUIZ)
        yield {f["kind"]: f for f in page.evaluate(EXTRACT_JS)}
        browser.close()


def test_finds_each_visible_field_once(fields):
    assert sorted(fields) == ["checkbox", "radio", "select", "text"]


def test_radio_group(fields):
    f = fields["radio"]
    assert f["question"] == "What color is the sky?"
    assert [o["label"] for o in f["options"]] == ["Blue", "Green"]


def test_checkbox_group(fields):
    f = fields["checkbox"]
    assert f["question"] == "Which are prime?"
    assert [o["label"] for o in f["options"]] == ["2", "4", "5"]


def test_select_skips_placeholder(fields):
    f = fields["select"]
    assert f["question"] == "Capital of France"
    assert [o["value"] for o in f["options"]] == ["paris", "rome"]


def test_text_field(fields):
    f = fields["text"]
    assert f["question"] == "Full name"
    assert f["filled"] is False
