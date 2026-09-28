"""
Jev navigates a web quiz in a browser.

Jev doesn't generate text or see screenshots. This module is its eyes and hands:
it reads each question and its options from the page, asks Jev to pick, and clicks.
Every decision goes to runs/<timestamp>.jsonl so you can score it later.
"""
import json
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import Error as PlaywrightError

from .jev import decide

HERE = Path(__file__).parent
EXTRACT_JS = (HERE / "extract.js").read_text()
CLICK_TARGET_JS = (HERE / "page.js").read_text()
BANNERS_JS = (HERE / "banners.js").read_text()
BLOCK_HTML_JS = (HERE / "blockhtml.js").read_text()
NAV_JS = (HERE / "nav.js").read_text()
# A tile has no checked state, so compare it and its surroundings before and after the click.
TILE_STATE_JS = "s => { const e = document.querySelector(s); return e ? e.outerHTML + e.parentElement.outerHTML : '' }"


def press_start(page, texts):
    """Click each text in order, e.g. a quiz's Start button, waiting for the page to react after each."""
    for text in texts:
        page.get_by_text(text).first.click(timeout=10000)
        time.sleep(2)


def changed(page, sel, before, read=None, wait=1.0):
    """Whether a tile looks different from before, checking for up to `wait` seconds as it restyles.
    `read` gets the state to compare; the default reads the tile and its surroundings."""
    end = time.time() + wait
    while True:
        if (read(sel) if read else page.evaluate(TILE_STATE_JS, sel)) != before:
            return True
        if time.time() > end:
            return False
        time.sleep(0.2)

# A question block with more text pieces than this likely holds site text too, so Jev picks the pieces.
# Merriam-Webster has 5: progress, timer, score, and difficulty around the question.
NOISY_PIECES = 4

# The whole label must be a navigation word, so "Next (Shift + N)" on an ad's video player doesn't match.
ARROW = r"[›>→»❯❱▸▶►⟩〉]"
NEXT_RE = re.compile(
    rf"^\s*(next|continue|forward|proceed|save (and|&) (next|continue)|submit answer)"
    rf"(\s+(question|page|step|section))?\s*{ARROW}?\s*$|^\s*{ARROW}\s*$", re.I)
SUBMIT_RE = re.compile(
    rf"^\s*(submit|finish|done|send|complete|end)(\s+(my|your|all))?(\s+(test|exam|assessment|quiz|answers?))?"
    rf"\s*[!.]?\s*{ARROW}?\s*$", re.I)

# "Select any 2", "you need to select 2 options", "choose up to 3": how many checkboxes the question wants.
COUNT_RE = re.compile(r"\b(?:select|choose|pick|tick|check|mark)\s+(?:(any|exactly|up to|at most|no more than|at least)\s+)?"
                      r"(\d+|one|two|three|four|five|six)\b(?!\s+or\s+more)", re.I)
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def pick_count(text):
    """(fewest, most) checkboxes the text asks for, or None if it doesn't say."""
    m = COUNT_RE.search(text)
    if not m:
        return None
    n = int(NUMBERS.get(m[2].lower(), m[2]))
    word = (m[1] or "").lower()
    return (1, n) if word in ("up to", "at most", "no more than") else (n, 99) if word == "at least" else (n, n)


def within_count(probs, count):
    """Which options to tick: Jev's yes answers, then the most likely added or the least likely dropped to meet
    `count`, the (fewest, most) the question allows."""
    ticks = [p >= 0.5 for p in probs]
    if count:
        ranked = sorted(range(len(probs)), key=lambda i: -probs[i])
        n = min(max(sum(ticks), count[0]), count[1], len(probs))
        ticks = [i in ranked[:n] for i in range(len(probs))]
    return ticks


# Error messages a page shows, e.g. Google Forms' "You need to select two choices" when Next is refused.
ALERTS_JS = ("() => [...document.querySelectorAll('[role=alert]')].filter(e => e.offsetWidth || e.offsetHeight)"
             ".map(e => e.innerText.trim()).filter(Boolean)")

# Buttons that run the quiz rather than answer it. A group of tiles holding one is not a question.
CONTROL_RE = re.compile(r"^\s*(start|begin|restart|retry|try again|play again|take (it|the quiz) again|share|"
                        rf"finish|see (my )?results?|show (my )?results?)(\s+(the\s+)?quiz)?\s*[!.]?\s*{ARROW}?\s*$", re.I)


def is_control(label):
    return bool(NEXT_RE.search(label) or SUBMIT_RE.search(label) or CONTROL_RE.search(label))


def without_controls(f):
    """A tile group minus any quiz controls in it, e.g. a Next button in the row of answers.
    None if fewer than two answers remain. A control's label that looks like the answers in markup
    is an answer, e.g. "begin" in a vocabulary quiz."""
    if not any(o.get("tile") for o in f.get("options", [])):
        return f
    looks = {o.get("look") for o in f["options"] if not is_control(o["label"])} - {None}
    options = [o for o in f["options"] if not is_control(o["label"]) or o.get("look") in looks]
    return {**f, "options": options} if len(options) >= 2 else None


def field_keys(f):
    """Identifies a field three ways, so it's answered once, and matching any one counts. The page may
    re-render it with new elements, redraw its labels in place (MathJax typesetting a formula), or add
    feedback to its question. A new question in reused elements matches none: its text and labels differ."""
    options = f.get("options", [])
    labels = tuple(o["label"] for o in options)
    element = f.get("sel") or tuple(o["sel"] for o in options)  # dropdown or text box, else the group's inputs
    return {(f["kind"], f["question"], labels), (f["kind"], f["question"], element),
            (f["kind"], element, labels)}  # feedback text such as "Correct!" can change the question block


class Session:
    def __init__(self, page, provider, role, log_path, info=None, min_confidence=0.6, submit=False, pause=True):
        self.page = page
        self.provider = provider
        self.role = role
        self.info = info or {}
        self.min_confidence = min_confidence
        self.submit = submit
        self.pause = pause
        self.log = log_path.open("a")

    def record(self, **entry):
        self.log.write(json.dumps({"provider": self.provider.name, **entry}) + "\n")
        self.log.flush()

    def ask(self, state, questions):
        """Call Jev. Returns None on a network or API error, so the caller can hand off to you."""
        try:
            return decide(self.provider, state, questions)
        except (requests.RequestException, KeyError, ValueError) as e:
            print(f"   ⚠ Jev request failed: {e}")
            return None

    def set_checked(self, sel, on=True):
        """Tick or untick with a real click, like a person would.

        Many quiz sites hide the real input under a styled answer tile and never tick it, so we
        click the tile when something covers the input. Returns whether the page took the click:
        the input is set as asked, or the tile we clicked changed.
        """
        if self.page.is_checked(sel) == on:
            return True
        for attempt in range(2):
            target = self.page.evaluate(CLICK_TARGET_JS, sel)
            before = self.page.evaluate(TILE_STATE_JS, target)
            try:
                self.page.click(target, timeout=3000)
            except PlaywrightError:
                self.dismiss_banners()  # banners often load late and cover the page; retry once
                continue
            if self.page.is_checked(sel) == on:
                return True
            return target != sel and changed(self.page, target, before)
        # Still blocked. Click from inside the page; plain forms accept this, some quiz sites ignore it.
        self.page.eval_on_selector(sel, "e => e.click()")
        return self.page.is_checked(sel) == on

    def dismiss_banners(self):
        """Click consent and cookie buttons that cover the page."""
        if not self.page.evaluate(BANNERS_JS):
            return
        for b in self.page.locator("[data-jev-dismiss]").all():
            try:
                label = b.inner_text().strip()
                b.click(timeout=2000)
                print(f"   (dismissed banner: {label!r})")
            except PlaywrightError:
                pass

    def wait_for_fields(self, done=frozenset(), timeout=10):
        """Pages built by JavaScript can show their questions a few seconds after loading.
        Fields matching a key in `done` were answered already and don't count."""
        end = time.time() + timeout
        while True:
            fields = [f for f in self.page.evaluate(EXTRACT_JS) if not field_keys(f) & done]
            if fields or time.time() > end:
                return fields
            time.sleep(0.5)

    def ask_human(self, question, reason="Not confident"):
        """Returns True if you answered; False means carry on without you."""
        if not self.pause:
            print(f"   ⚠ {reason}, not pausing (--no-pause)")
            return False
        self.record(question=question, answered_by="human", reason=reason)
        input(f"   ⚠ {reason} on: {question!r}\n   Answer it yourself in the browser, then press Enter… ")
        return True

    def question_text(self, f):
        """The question to ask Jev about. A noisy block goes to Jev one piece at a time, to keep only the question."""
        pieces = f.get("pieces") or []
        if len(pieces) <= NOISY_PIECES:
            return f["question"]
        state = {"answer_options": [o["label"] for o in f["options"]],
                 "question_block_html": self.page.evaluate(BLOCK_HTML_JS, f["block"])}
        answers = self.ask(state, {f"p{i}": {
            "type": "noul",
            "instructions": "Is this text part of the quiz question (including any passage, table, or formula it "
                            f"needs), rather than an answer option, explanation, button, or site text? Text: {p!r}",
        } for i, p in enumerate(pieces)})
        try:
            kept = [p for i, p in enumerate(pieces) if answers[f"p{i}"]["noul"] >= 0.5]
        except (TypeError, KeyError):
            return f["question"]
        print(f"   (question block had {len(pieces)} text pieces; Jev kept {len(kept)})")
        return " ".join(kept) or f["question"]

    def answer_single(self, f):
        """Radio group or dropdown: one Choice question over the visible options."""
        labels = [o["label"] or f"option {i}" for i, o in enumerate(f["options"])]
        criteria = {f"opt{i}": label for i, label in enumerate(labels)}
        question = self.question_text(f)
        print(f" Q: {question[:100]!r} [{f['kind']}]")
        state = {"role": self.role, "assessment_question": question}
        if f.get("hint"):
            state["question_notes"] = f["hint"]
        answers = self.ask(state, {"pick": {
            "type": "choice",
            "instructions": "Which option is the correct answer to the assessment question?",
            "criteria": criteria,
        }})
        a = (answers or {}).get("pick") or {}
        if a.get("choice") not in criteria:
            self.ask_human(f["question"], "No usable answer from Jev")
            return
        idx = int(a["choice"][3:])
        print(f"   → {labels[idx]!r} (confidence {a['confidence']:.2f})")
        entry = dict(question=question, kind=f["kind"], options=labels, choice=labels[idx], confidence=a["confidence"])
        option = f["options"][idx]
        if a["confidence"] < self.min_confidence and option.get("tile") and not self.pause:
            # Tiles are a guess at what the answers are, and low confidence often means these aren't answers
            # at all, e.g. JetPunk's Refresh and Create Account buttons after the last question.
            print("   (skipped: not confident, and answer tiles could be site buttons. Answer it yourself if needed.)")
            return
        if a["confidence"] < self.min_confidence:
            if self.pause:
                self.record(**entry)  # you pick, so no click to check
            if self.ask_human(f["question"]):
                return
        if f["kind"] == "select" and option.get("sel"):  # an ARIA dropdown: open it, then click the option
            try:
                self.page.click(f["sel"], timeout=5000)
                # Google Forms copies the options into a popup, ids included, so click the copy you can see.
                self.page.locator(option["sel"]).locator("visible=true").first.click(timeout=5000)
                checked = changed(self.page, option["sel"], False,
                                  lambda s: self.page.get_attribute(s, "aria-selected") == "true")
            except PlaywrightError:
                print("   ⚠ Couldn't pick from the dropdown")
                checked = False
        elif f["kind"] == "select":
            self.page.select_option(f["sel"], option["value"])
            checked = self.page.input_value(f["sel"]) == option["value"]
        elif option.get("tile"):
            before = self.page.evaluate(TILE_STATE_JS, option["sel"])
            try:
                self.page.click(option["sel"], timeout=5000)
                checked = changed(self.page, option["sel"], before)
            except PlaywrightError:
                print("   ⚠ Couldn't click the answer tile")
                checked = False
        else:
            checked = self.set_checked(option["sel"])
        # Whether the page took the pick: the input is set, or the tile clicked changed. False flags a click
        # to check, not a certain failure.
        self.record(**entry, checked=checked)

    def answer_checkboxes(self, f):
        """Select-all-that-apply: one Noul per option, all in a single parallel request.

        Each question can't see the others, so the full option list goes in the state.
        """
        labels = [o["label"] for o in f["options"]]
        question = self.question_text(f)
        print(f" Q: {question[:100]!r} [checkbox]")
        state = {"role": self.role, "assessment_question": question, "all_options": labels}
        if f.get("hint"):
            state["question_notes"] = f["hint"]
        qs = {f"opt{i}": {"type": "noul",
                          "instructions": f"Is this option a correct answer to the question: {label!r}?"}
              for i, label in enumerate(labels)}
        answers = self.ask(state, qs)
        try:
            probs = [answers[f"opt{i}"]["noul"] for i in range(len(labels))]
        except (TypeError, KeyError):
            self.ask_human(f["question"], "No usable answer from Jev")
            return
        count = pick_count(f"{question} {f.get('hint', '')}") or ((1, 99) if f.get("required") else None)
        ticks = within_count(probs, count)
        for label, p, t in zip(labels, probs, ticks):
            print(f"   {'☑' if t else '☐'} {label!r} (p={p:.2f})")
        if ticks != [p >= 0.5 for p in probs]:
            print("   (the question limits how many to tick, so the tool kept Jev's most likely)")
        if any(0.35 < p < 0.65 for p in probs):
            if self.pause:
                self.record(question=question, kind="checkbox", options=labels, probs=probs)
            if self.ask_human(f["question"]):
                return
        checked = all([self.set_checked(o["sel"], t) for o, t in zip(f["options"], ticks)])
        self.record(question=question, kind="checkbox", options=labels, probs=probs, checked=checked)

    def answer_text(self, f):
        """Text box: fill identity fields from your info. Open-ended answers go to you."""
        if f.get("filled"):
            return
        if f.get("multiline"):
            print("   (skipped: multi-line text box, such as a comment or essay. Fill it yourself if needed.)")
            return
        if not self.info:
            self.ask_human(f["question"], "Text field")
            return
        criteria = {k: f"The field asks for the person's {k.replace('_', ' ')}" for k in self.info}
        criteria["none"] = "The field asks for something else, such as a written answer"
        answers = self.ask({"field_label": f["question"]}, {"which": {
            "type": "choice",
            "instructions": "Which of the person's saved facts belongs in this form field?",
            "criteria": criteria,
        }})
        a = (answers or {}).get("which") or {}
        if a.get("choice") not in self.info or a["confidence"] < self.min_confidence:
            self.ask_human(f["question"], "Text field")
            return  # Jev can't write text, so nothing to fall back on
        print(f"   → {a['choice']} (confidence {a['confidence']:.2f})")
        self.page.fill(f["sel"], self.info[a["choice"]])

    def refused(self, before, url, wait=2.0):
        """Error messages that appeared after clicking Next, checking for up to `wait` seconds.
        Empty once the page moves on."""
        end = time.time() + wait
        while time.time() < end:
            time.sleep(0.3)
            try:
                if self.page.url != url:
                    return []
                errors = [e for e in self.page.evaluate(ALERTS_JS) if e not in before]
            except PlaywrightError:
                return []  # the page is navigating
            if errors:
                return errors
        return []

    def click_forward(self):
        """Click Next/Continue. Returns False when finished or stopping at Submit."""
        for i, label in enumerate(self.page.evaluate(NAV_JS)):
            b = self.page.locator(f'[data-jev-nav="{i}"]')
            if NEXT_RE.search(label):
                before, url = set(self.page.evaluate(ALERTS_JS)), self.page.url
                b.click()
                if not (errors := self.refused(before, url)):
                    return True
                print(f"\n⚠ The page didn't move on. It says: {'; '.join(errors)[:300]}")
                self.record(stuck=errors)
                if self.pause:
                    input("   Fix what it flags, click Next yourself, then press Enter… ")
                    return True
                return False
            if SUBMIT_RE.search(label):
                if not self.submit:
                    print("\n✋ Reached Submit. Review the answers and click it yourself.")
                    return False
                b.click()
                return False
        print("\nNo Next or Submit button. This looks like the last page.")
        return False

    def quiz_fields(self, fields):
        """Jev decides which fields belong to the quiz, so search boxes, language pickers, quiz settings,
        and comment forms stay untouched. If the request fails, all fields count, as before."""
        fields = [g for g in map(without_controls, fields) if g]
        if not fields:
            return fields
        for f in fields:  # rate what the question really is, not the site text around it
            if f.get("pieces") and len(f["pieces"]) > NOISY_PIECES:
                f["question"], f["pieces"] = self.question_text(f), None
        described = [f"{f['kind']} field. Question or label: {f['question'][:300]!r}."
                     + (f" Options: {[o['label'][:60] for o in f['options'][:8]]}." if f.get("options") else "")
                     + f" Nearby text: {f.get('context', '')!r}"
                     for f in fields]
        answers = self.ask({"page_title": self.page.title(), "page_fields": described}, {f"f{i}": {
            "type": "noul",
            "instructions": "Is this field part of the quiz or form the person came to fill in: one of its "
                            "questions, or a detail it asks about the person? Say no for site search, navigation, "
                            "language or translation, quiz settings, newsletter sign-up, login, comments, and buttons that "
                            "control the quiz, such as start, finish, retry, or share. Also say no when the options are "
                            "not possible answers to the question, such as account or page buttons. "
                            f"Field: {d}",
        } for i, d in enumerate(described)})
        try:
            probs = [answers[f"f{i}"]["noul"] for i in range(len(fields))]
        except (TypeError, KeyError):
            return fields
        keep = []
        for f, p in zip(fields, probs):
            self.record(question=f["question"], kind=f["kind"], part_of_quiz=p)
            if p >= 0.65:
                keep.append(f)
            elif p >= 0.35:
                self.ask_human(f["question"], f"Not sure this field is part of the quiz (p={p:.2f})")
            else:
                print(f" (skipped, not part of the quiz: {f['question'][:70]!r} [{f['kind']}], p={p:.2f})")
        return keep

    def answer(self, f):
        if f["kind"] in ("radio", "select"):
            self.answer_single(f)
        elif f["kind"] == "checkbox":
            self.answer_checkboxes(f)
        else:
            print(f" Q: {f['question'][:100]!r} [{f['kind']}]")
            self.answer_text(f)

    def run(self, max_pages=200):
        # Answered fields, kept while the page stays loaded: a quiz that swaps questions in place may leave
        # the old ones in the page, e.g. scrolled out of view. A new page load restarts the data-jev ids,
        # so its keys could match old ones by chance; then start over.
        done, doc = set(), None
        for step in range(1, max_pages + 1):
            self.page.wait_for_load_state("domcontentloaded")
            time.sleep(0.8)  # let single-page apps finish rendering
            if doc != (doc := self.page.evaluate("performance.timeOrigin")):
                done = set()
            fields = self.wait_for_fields(done)
            before = set(done)  # answered on earlier pages
            print(f"\n— Page {step}: {len(fields)} field(s)")
            self.dismiss_banners()
            # Some quizzes are one long page that reveals questions as you answer, so keep
            # checking for new ones until none appear. Answered fields are skipped (see field_keys).
            answered = 0
            for _ in range(50):
                if not fields:
                    break
                for f in fields:
                    done |= field_keys(f)
                for f in self.quiz_fields(fields):
                    self.answer(f)
                    answered += 1
                time.sleep(0.5)
                fields = [f for f in self.page.evaluate(EXTRACT_JS) if not field_keys(f) & done]
            if not answered:
                left = self.page.evaluate(EXTRACT_JS)
                if step > 1 and left and all(field_keys(f) & before for f in left):
                    # Only answered questions: Next was refused, or the page redrew the same questions.
                    print("\n⚠ The page didn't move on after Next. Check it for an error message.")
                else:
                    # A Next button here could lead anywhere, such as another quiz, so don't guess.
                    print("\nFound no quiz questions on this page, so stopping here.")
                break
            if not self.click_forward():
                break
