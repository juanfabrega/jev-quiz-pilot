import argparse

import pytest

from jev_quiz_pilot.cli import build_parser, name_parts, normalize_url, parse_info, rerun_command


def test_parse_info():
    assert parse_info(["email=a@b.c", "full_name=Jane Q Doe"]) == {"email": "a@b.c", "full_name": "Jane Q Doe"}
    with pytest.raises(argparse.ArgumentTypeError):
        parse_info(["email"])


def test_name_parts():
    assert name_parts("Jane Q Doe") == {"first_name": "Jane", "last_name": "Q Doe"}
    assert name_parts("Cher") == {"first_name": "Cher"}


def test_rerun_command_round_trips():
    args = build_parser().parse_args(["--role", "You are a CPA.", "--submit"])
    info = {"full_name": "Jane Doe", "email": "jane@example.com"}
    assert rerun_command(args, info) == (
        "jev-quiz-pilot --yes --role 'You are a CPA.' "
        "--info 'full_name=Jane Doe' --info email=jane@example.com --submit"
    )


def test_normalize_url(tmp_path):
    quiz = tmp_path / "quiz.html"
    quiz.write_text("<html></html>")
    assert normalize_url(str(quiz)) == quiz.resolve().as_uri()
    assert normalize_url("example.com/quiz") == "https://example.com/quiz"
    assert normalize_url("http://localhost:8000/q") == "http://localhost:8000/q"


def test_rerun_command_puts_url_first():
    args = build_parser().parse_args(["https://example.com/quiz", "--no-pause"])
    assert rerun_command(args, {}) == "jev-quiz-pilot https://example.com/quiz --yes --no-pause"
