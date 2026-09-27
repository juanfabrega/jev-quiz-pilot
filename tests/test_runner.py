import pytest

from jev_quiz_pilot.runner import NEXT_RE, SUBMIT_RE, is_control_group


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
    assert is_control_group(tiles(*labels))


def test_answer_tiles_are_a_question():
    assert not is_control_group(tiles("17 years", "49 years", "Start of the war"))
