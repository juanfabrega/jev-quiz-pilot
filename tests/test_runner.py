import pytest

from jev_quiz_pilot.runner import NEXT_RE, SUBMIT_RE, pick_count, within_count, without_controls


@pytest.mark.parametrize("label", ["Next", "next question", "Continue →", "›", "Save & Next", "Proceed", "Next ❯"])
def test_next_matches_navigation(label):
    assert NEXT_RE.search(label)


@pytest.mark.parametrize("label", ["Next (Shift + N)", "Next up: 10 more quizzes", "Continue reading", "Contact"])
def test_next_ignores_other_buttons(label):
    assert not NEXT_RE.search(label)


@pytest.mark.parametrize("label", ["Submit", "Finish quiz", "Submit answers", "Done", "Submit my Answers!", "Finish ❯"])
def test_submit_matches(label):
    assert SUBMIT_RE.search(label)


@pytest.mark.parametrize("label", ["Submit a correction", "Send us a tip", "Done reading? Share this"])
def test_submit_ignores_other_buttons(label):
    assert not SUBMIT_RE.search(label)


def tiles(*labels):
    return {"kind": "radio", "question": "q", "options": [{"label": x, "sel": "s", "tile": True} for x in labels]}


@pytest.mark.parametrize("labels", [("Finish Quiz", "Try again"), ("Share", "Play again"), ("Start", "Next")])
def test_quiz_control_tiles_are_not_a_question(labels):
    assert without_controls(tiles(*labels)) is None


def test_answer_tiles_are_a_question():
    f = tiles("17 years", "49 years", "Start of the war")
    assert without_controls(f) == f


def test_a_next_button_beside_the_answers_is_dropped():
    f = without_controls(tiles("enemy", "actor", "builder", "Next"))
    assert [o["label"] for o in f["options"]] == ["enemy", "actor", "builder"]


def test_a_control_word_styled_like_the_answers_is_an_answer():
    f = tiles("publish", "restrict", "correct", "begin")
    for o in f["options"]:
        o["look"] = "A choice choice-"
    assert without_controls(f) == f


def test_a_next_button_styled_unlike_the_answers_is_dropped():
    f = tiles("enemy", "actor", "builder", "Next")
    for o in f["options"]:
        o["look"] = "DIV question-gstage__next" if o["label"] == "Next" else "A choice choice-"
    assert [o["label"] for o in without_controls(f)["options"]] == ["enemy", "actor", "builder"]


@pytest.mark.parametrize("text, count", [
    ("Holiday activities you enjoy - Select any 2", (2, 2)),
    ("In this example, you need to select 2 options.", (2, 2)),
    ("Choose up to three answers", (1, 3)),
    ("Tick at least 2 boxes", (2, 99)),
    ("Select all that apply", None),
    ("Select one or more", None),
    ("Check your answers before you submit", None),
])
def test_pick_count(text, count):
    assert pick_count(text) == count


def test_within_count_keeps_the_most_likely():
    probs = [0.75, 0.68, 0.74, 0.75, 0.67]
    assert within_count(probs, (2, 2)) == [True, False, False, True, False]
    assert within_count([0.2, 0.4, 0.1], (2, 2)) == [True, True, False]
    assert within_count([0.9, 0.2], None) == [True, False]
    assert within_count([0.9, 0.8, 0.7], (1, 2)) == [True, True, False]
