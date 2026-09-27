"""Benchmark cases: real quiz pages, and what a working harness should find on each.

The benchmark scores the harness, not Jev. So each case says where the quiz's questions really are,
using selectors written by hand for that site, never our own extractor:

  block     one element per question
  question  the question text inside the block. Leave out to use the block's text minus the options.
  option    each answer option inside the block
  exclude   parts of the block that are not question text, such as explanations or buttons

Other keys:
  url       the page to open
  start     texts to click before the run, in order, standing in for you pressing Start
  total     how many questions the whole quiz has. Catches a run that stops early.
  end       "submit" if the run should stop at the quiz's final Submit button
  stay      a URL prefix the run must not leave, e.g. clicking into another quiz
  live      True if the page can't be replayed from a snapshot

A case with no block expects no questions: the harness must answer nothing on that page.
"""
from pathlib import Path

DEMO = (Path(__file__).parent.parent / "docs" / "demo" / "index.html").resolve().as_uri()

CASES = {
    # Our own demo: fieldsets, a dropdown, checkboxes, three pages.
    "demo": dict(
        url=DEMO, total=9, end="submit", stay=DEMO, live=True,  # a local file needs no snapshot
        block="fieldset, .field", question="legend, .field > label",
        option="fieldset > label, option:not([value=''])",
    ),
    # One long page, plain divs, no fieldsets. Final button reads "Submit my Answers!".
    "funtrivia": dict(
        url="https://www.funtrivia.com/trivia-quiz/General/General-Knowledge-Questions-37732.html",
        total=25, end="submit",
        block=".playquiz_qnbox", question=".playquiz_qntxtbox b", option="label.choicefield",
    ),
    # Styled radios (iCheck) with an overlay inside each label. Grades each answer on click.
    "proprofs": dict(
        url="https://www.proprofs.com/quiz-school/story.php?title=pp-free-general-knowledge-quiz",
        block=".ques-answer-box", question="h2.question_count_text", option=".m_opttxt",
    ),
    # SAT questions with passages, tables, and MathJax formulas. Hidden worked solutions.
    "mometrix": dict(
        url="https://www.mometrix.com/academy/sat-practice-test/",
        total=5,
        block=".ipq-question", option="label.ipq-choice", exclude=".ipq-explanation, button, a",
    ),
    # One question per page, "Next ❯" button, server round trip per page. There is no Submit button:
    # the last "Next ❯" submits, so the run ends on the results page.
    "w3schools": dict(
        url="https://www.w3schools.com/quiztest/quiztest.asp?qtest=JS",
        total=25, stay="https://www.w3schools.com/quiztest/", live=True,  # recording it hangs
        block="#quizcontainer", question="#qtext", option="label.radiocontainer",
    ),
    # Answer tiles are plain divs: no inputs, roles, or tabindex. Needs Start first.
    "jetpunk": dict(
        url="https://www.jetpunk.com/quizzes/multiple-choice-general-knowledge-1",
        start=["Start Quiz"], stay="https://www.jetpunk.com/quizzes/multiple-choice-general-knowledge-1",
        block=".question", option=".choice-text",
    ),
    # Not quizzes at the start: exam settings, Google Translate, and a comment form.
    "4tests-settings": dict(url="https://www.4tests.com/sat", live=True),  # the snapshot never finishes loading
    "quizquestions-article": dict(url="https://quizquestions.uk/multiple-choice-quiz/"),
}
