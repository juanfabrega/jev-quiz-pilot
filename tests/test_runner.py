import pytest

from jev_quiz_pilot.runner import NEXT_RE, SUBMIT_RE


@pytest.mark.parametrize("label", ["Next", "next question", "Continue →", "›", "Save & Next", "Proceed"])
def test_next_matches_navigation(label):
    assert NEXT_RE.search(label)


@pytest.mark.parametrize("label", ["Next (Shift + N)", "Next up: 10 more quizzes", "Continue reading", "Contact"])
def test_next_ignores_other_buttons(label):
    assert not NEXT_RE.search(label)


@pytest.mark.parametrize("label", ["Submit", "Finish quiz", "Submit answers", "Done"])
def test_submit_matches(label):
    assert SUBMIT_RE.search(label)


@pytest.mark.parametrize("label", ["Submit a correction", "Send us a tip", "Done reading? Share this"])
def test_submit_ignores_other_buttons(label):
    assert not SUBMIT_RE.search(label)
