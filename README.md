<p align="center">
  <img src="docs/hero.png" alt="Terminal running jev-quiz-pilot, showing the JEV QUIZ PILOT banner in block letters" width="640">
</p>

<h1 align="center">Jev Quiz Pilot</h1>

<p align="center"><b>Put Jev in the pilot's seat of a web quiz, and measure how it does.</b></p>

<p align="center">
  <a href="https://github.com/juanfabrega/jev-quiz-pilot/actions/workflows/tests.yml"><img src="https://github.com/juanfabrega/jev-quiz-pilot/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <a href="https://docs.typesafe.ai"><img src="https://img.shields.io/badge/powered%20by-Jev%201.13-58a6ff" alt="Powered by Jev 1.13"></a>
  <img src="https://img.shields.io/badge/browser-Playwright-2EAD33?logo=playwright&logoColor=white" alt="Playwright">
</p>

Let Jev 1.13, TypeSafe's decision model, navigate a web quiz in a browser, so you can measure how well it does. The tool reads each question and its options from the page, asks Jev to pick, clicks the answer, and moves to the next page. Jev does not see screenshots or write text.

## See it run

### A multi-page quiz

Jev takes our three-page [demo quiz](https://juanfabrega.github.io/jev-quiz-pilot/demo/): a name field, radio buttons, dropdowns, and "select all" checkboxes. It scores 9 out of 9.

<p align="center">
  <img src="docs/demo.gif" alt="Jev takes a three-page general knowledge quiz. The quiz is on the left; the CLI output with each pick and its confidence is on the right. Jev scores 9 out of 9." width="900">
</p>

Try it yourself. After [Setup](#setup), run:

```sh
uv run jev-quiz-pilot https://juanfabrega.github.io/jev-quiz-pilot/demo/ --submit
```

### A real-world site

Jev takes a 35-question [BuzzFeed trivia quiz](https://www.buzzfeed.com/audreyworboys/general-knowledge-trivia-quiz-71): one long page with ads and a cookie banner. The tool dismisses the banner, clicks each answer tile, and skips the comment box. Jev scores 31 out of 35.

<p align="center">
  <img src="docs/demo-buzzfeed.gif" alt="Jev takes a 35-question BuzzFeed trivia quiz on one long scrolling page. The page is on the left; the CLI output is on the right. BuzzFeed's result card shows 31 out of 35 correct." width="800">
</p>

```sh
uv run jev-quiz-pilot https://www.buzzfeed.com/audreyworboys/general-knowledge-trivia-quiz-71 --no-pause
```

## Acceptable use

Use this on practice quizzes, your own forms, and quizzes you have permission to automate. Do not use it on graded, proctored, or certification tests. That is cheating, and most testing sites ban automation in their terms.

By default the tool stops before the final Submit button so you can review the answers.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
cp .env.example .env   # then add one API key
```

Use either provider. Set the key for the one you have:

| Provider | Key | Model sent |
|---|---|---|
| [TypeSafe](https://docs.typesafe.ai) (direct) | `TYPESAFE_API_KEY` | `jev-1.13.0` |
| [OpenRouter](https://openrouter.ai/typesafe) | `OPENROUTER_API_KEY` | `typesafe/jev-1.13` |

If both keys are set, the tool uses TypeSafe. Pass `--provider openrouter` to override. Both providers run the same model, so you can compare results.

The tool opens the quiz in your installed Google Chrome. Without Chrome, it uses Playwright's Chromium; install it once with `uv run playwright install chromium`.

## Run

Pass the quiz URL:

```sh
uv run jev-quiz-pilot https://example.com/quiz
```

A browser window opens at the quiz. The tool then:

1. Asks who Jev should act as, and your name and email for identity fields. Press Enter to skip any question.
2. Prints the matching command, so later runs need no prompts.
3. Waits while you log in or open the first question, if needed. Press Enter to start.
4. Answers each page and clicks Next. It stops before the final Submit unless you pass `--submit`.
5. Keeps the window open until you press Enter, so you can review the answers.

Repeat runs skip the prompts:

```sh
uv run jev-quiz-pilot https://example.com/quiz --yes --role "You are a trained CPA. Pick the correct answer to each question."
```

A local HTML file works too: `uv run jev-quiz-pilot docs/demo/index.html`.

### Use your own Chrome

The new window starts logged out. If a quiz needs your saved logins, attach to your own Chrome instead. Start Chrome with remote debugging; it needs its own profile folder.

macOS:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 --user-data-dir=/tmp/jev-chrome
```

Windows:

```bat
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=%TEMP%\jev-chrome
```

Open the quiz in that window, then run:

```sh
uv run jev-quiz-pilot --cdp-url http://localhost:9222
```

## Options

| Flag | Purpose |
|---|---|
| `URL` | First argument. The quiz to open: a web address or a local HTML file. |
| `--role TEXT` | Who Jev acts as. Keep it short; unrelated text lowers accuracy. |
| `--info KEY=VALUE` | A fact for identity fields, such as `full_name="Jane Doe"` or `email=jane@example.com`. Repeatable. |
| `--min-confidence N` | Below this, the tool pauses so you answer. Default `0.6`. |
| `--submit` | Click the final Submit button. Off by default. |
| `--no-pause` | Never wait for you. On low confidence, use Jev's pick anyway. |
| `--provider NAME` | `auto`, `typesafe`, or `openrouter`. Default `auto` uses whichever key is set, TypeSafe first. |
| `-y`, `--yes` | Skip the setup prompts. |
| `--cdp-url URL` | Attach to your own Chrome instead of opening a new window. See [Use your own Chrome](#use-your-own-chrome). |

## How it works

Jev never sees the page. It doesn't read screenshots or write text; it only makes typed decisions. The tool is Jev's eyes and hands: it reads each question from the page, asks Jev to pick, and clicks the answer.

```mermaid
flowchart TD
    open["Open the quiz<br/>(new window, or your Chrome with --cdp-url)"] --> read["Read the page's fields<br/>extract.js"]
    read --> banners["Dismiss cookie banners"]
    banners --> ask["Ask Jev about the next field"]
    ask --> sure{"Confident?"}
    sure -- yes --> answer["Click the answer<br/>or the tile drawn over it"]
    sure -- no --> you["Pause so you answer<br/>(--no-pause: use Jev's pick)"]
    answer --> reread["Re-read the page<br/>for fields that just appeared"]
    you --> reread
    reread --> more{"More fields?"}
    more -- yes --> ask
    more -- no --> button{"Button?"}
    button -- Next --> read
    button -- "Submit, or none" --> stop["Stop for your review<br/>(--submit: click it)"]
```

### What Jev receives

Each field becomes one request: a `state` holding the question, plus a typed question over the options. This is a real request and answer for a radio question:

```jsonc
// Request
{
  "model": "jev-1.13.0",
  "state": {
    "role": "You are a trivia champion. Pick the correct answer to each question.",
    "assessment_question": "What is the capital of Australia?"
  },
  "questions": {
    "pick": {
      "type": "choice",
      "instructions": "Which option is the correct answer to the assessment question?",
      "criteria": { "opt0": "Sydney", "opt1": "Melbourne", "opt2": "Canberra", "opt3": "Perth" }
    }
  }
}

// Answer
{ "pick": { "type": "choice", "choice": "opt2", "confidence": 1,
            "probabilities": { "opt0": 0, "opt1": 0, "opt2": 1, "opt3": 0 } } }
```

The tool maps `opt2` back to "Canberra" and clicks it. Each field type uses a different request:

| Field | Request to Jev |
|---|---|
| Radio buttons, dropdown | One `choice` over the options. Below `--min-confidence`, the tool pauses. |
| Checkboxes | One `noul` (probability of yes) per option, all in one request. The option list goes in the `state`, since the questions can't see each other. Any probability between 0.35 and 0.65 pauses. |
| Text box | One `choice` over your `--info` keys, such as `full_name`. Anything else pauses. Multi-line boxes are skipped. |

If a request to Jev fails, the tool pauses for you on that field.

Every decision goes to `runs/<timestamp>.jsonl` with the provider, question, options, choice, and confidence. Compare it against the answer key to score Jev.

## Limits

- OpenRouter's decisions API is in alpha. It may change and break this tool.
- Field detection is generic. On unusual form builders, question text may come out garbled.
- Jev sees only the question text. Questions that depend on a passage, image, or table above them lose that context.
- Cost on OpenRouter: $0.042 per million input tokens, $0 output. See TypeSafe's site for direct pricing.

## Develop

```sh
uv run playwright install chromium   # once
uv run pytest
```

The tests load a local HTML quiz in headless Chromium. They need no API key.

To refresh the images in `docs/`:

```sh
uv run python docs/render_images.py   # hero.png and social-preview.png
uv run python docs/record_demo.py     # demo.gif and demo-buzzfeed.gif; needs an API key and ffmpeg
```

## License

MIT
