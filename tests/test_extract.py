"""Smoke test for extract.js: load a local quiz page in headless Chromium and check what it finds.

Needs no API key. Needs Chromium: uv run playwright install chromium
"""
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from jev_quiz_pilot.runner import EXTRACT_JS

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def extract():
    """Returns a function that loads a local page and runs extract.js on it."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def run(name):
            page.goto((HERE / name).as_uri())
            return page.evaluate(EXTRACT_JS)
        yield run
        browser.close()


@pytest.fixture(scope="module")
def fields(extract):
    return {f["kind"]: f for f in extract("quiz.html")}


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


@pytest.fixture(scope="module")
def block_fields(extract):
    return extract("quiz_blocks.html")


def test_question_comes_from_the_block_around_the_options(block_fields):
    """Not the first option's label, and not the hidden explanation or the link."""
    assert block_fields[0]["question"] == "1. Which chess piece is of the lowest relative value?"


def test_question_keeps_every_visible_piece_in_order(block_fields):
    f = block_fields[1]
    assert f["pieces"] == ["2. Prices are in the table below.", "Trees$25", "How much do two trees cost?"]
    assert "Submit" not in f["question"]


def test_formula_keeps_fractions_and_powers(block_fields):
    assert block_fields[2]["question"] == "3. Solve y=(1)/(4)x^(2) for y."


@pytest.fixture(scope="module")
def widget_fields(extract):
    return {f["kind"]: f for f in extract("quiz_widgets.html")}


def test_aria_radios_are_read_like_inputs(widget_fields):
    f = widget_fields["radio"]
    assert f["question"] == "What color is the sky?"
    assert [o["label"] for o in f["options"]] == ["Blue", "Green"]


def test_aria_checkboxes_in_a_list_are_one_question(widget_fields):
    assert sorted(widget_fields) == ["checkbox", "radio", "select", "text"]
    f = widget_fields["checkbox"]
    assert f["question"] == "Which are planets?"
    assert [o["label"] for o in f["options"]] == ["Mars", "Moon"]
    assert f["hint"] == "Select exactly 1."
    assert f["required"] and not widget_fields["radio"].get("required")


def test_aria_dropdown_is_read_without_its_placeholder(widget_fields):
    f = widget_fields["select"]
    assert f["question"] == "Which is the largest ocean?"
    assert [o["label"] for o in f["options"]] == ["Pacific", "Arctic"]
    assert all(o["sel"] for o in f["options"])


def test_text_box_label_comes_from_aria_labelledby(widget_fields):
    assert widget_fields["text"]["question"] == "Your first name"


def test_clickable_tiles_become_a_choice_outside_nav(extract):
    [f] = extract("quiz_tiles.html")
    assert f["question"] == "How many rings are on the Olympic flag?"
    assert [o["label"] for o in f["options"]] == ["4", "5", "6"]
    assert all(o["tile"] for o in f["options"])
