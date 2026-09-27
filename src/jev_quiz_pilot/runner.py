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
# A tile has no checked state, so compare it and its surroundings before and after the click.
TILE_STATE_JS = "s => { const e = document.querySelector(s); return e ? e.outerHTML + e.parentElement.outerHTML : '' }"

# A question block with more text pieces than this likely holds site text too, so Jev picks the pieces.
NOISY_PIECES = 6

# The whole label must be a navigation word, so "Next (Shift + N)" on an ad's video player doesn't match.
ARROW = r"[›>→»❯❱▸▶►⟩〉]"
NEXT_RE = re.compile(
    rf"^\s*(next|continue|forward|proceed|save (and|&) (next|continue)|submit answer)"
    rf"(\s+(question|page|step|section))?\s*{ARROW}?\s*$|^\s*{ARROW}\s*$", re.I)
SUBMIT_RE = re.compile(
    rf"^\s*(submit|finish|done|send|complete|end)(\s+(my|your|all))?(\s+(test|exam|assessment|quiz|answers?))?"
    rf"\s*[!.]?\s*{ARROW}?\s*$", re.I)

# Buttons that run the quiz rather than answer it. A group of tiles holding one is not a question.
CONTROL_RE = re.compile(r"^\s*(start|begin|restart|retry|try again|play again|take (it|the quiz) again|share|"
                        rf"finish|see (my )?results?|show (my )?results?)(\s+(the\s+)?quiz)?\s*[!.]?\s*{ARROW}?\s*$", re.I)


def is_control_group(f):
    return any(o.get("tile") for o in f.get("options", [])) and any(
        NEXT_RE.search(o["label"]) or SUBMIT_RE.search(o["label"]) or CONTROL_RE.search(o["label"])
        for o in f["options"])


def field_keys(f):
    """Identifies a field two ways, so it's answered once. By content: the page may re-render it with new
    elements. By element: the page may redraw its labels in place, e.g. MathJax typesetting a formula."""
    options = f.get("options", [])
    element = f.get("sel") or tuple(o["sel"] for o in options)  # dropdown or text box, else the group's inputs
    return {(f["kind"], f["question"], tuple(o["label"] for o in options)), (f["kind"], f["question"], element)}


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
        click the tile when something covers the input, and don't check the input's state after.
        """
        if self.page.is_checked(sel) == on:
            return
        for attempt in range(2):
            target = self.page.evaluate(CLICK_TARGET_JS, sel)
            try:
                self.page.click(target, timeout=3000)
                return
            except PlaywrightError:
                self.dismiss_banners()  # banners often load late and cover the page; retry once
        # Still blocked. Click from inside the page; plain forms accept this, some quiz sites ignore it.
        self.page.eval_on_selector(sel, "e => e.click()")

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

    def wait_for_fields(self, timeout=10):
        """Pages built by JavaScript can show their questions a few seconds after loading."""
        end = time.time() + timeout
        while True:
            fields = self.page.evaluate(EXTRACT_JS)
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
        state = {"role": self.role, "assessment_question": question}
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
        if a["confidence"] < self.min_confidence:
            if self.pause:
                self.record(**entry)  # you pick, so no click to check
            if self.ask_human(f["question"]):
                return
        option = f["options"][idx]
        if f["kind"] == "select":
            self.page.select_option(f["sel"], option["value"])
            checked = self.page.input_value(f["sel"]) == option["value"]
        elif option.get("tile"):
            before = self.page.evaluate(TILE_STATE_JS, option["sel"])
            self.page.click(option["sel"], timeout=5000)
            time.sleep(0.3)
            checked = self.page.evaluate(TILE_STATE_JS, option["sel"]) != before
        else:
            self.set_checked(f["options"][idx]["sel"])
            checked = self.page.is_checked(f["options"][idx]["sel"])
        # Whether the page took the pick: the input is ticked, or a tile changed. A site that styles tiles
        # over hidden inputs may never tick them, so False flags a click to check, not a certain failure.
        self.record(**entry, checked=checked)

    def answer_checkboxes(self, f):
        """Select-all-that-apply: one Noul per option, all in a single parallel request.

        Each question can't see the others, so the full option list goes in the state.
        """
        labels = [o["label"] for o in f["options"]]
        question = self.question_text(f)
        state = {"role": self.role, "assessment_question": question, "all_options": labels}
        qs = {f"opt{i}": {"type": "noul",
                          "instructions": f"Is this option a correct answer to the question: {label!r}?"}
              for i, label in enumerate(labels)}
        answers = self.ask(state, qs)
        try:
            probs = [answers[f"opt{i}"]["noul"] for i in range(len(labels))]
        except (TypeError, KeyError):
            self.ask_human(f["question"], "No usable answer from Jev")
            return
        for label, p in zip(labels, probs):
            print(f"   {'☑' if p >= 0.5 else '☐'} {label!r} (p={p:.2f})")
        if any(0.35 < p < 0.65 for p in probs):
            if self.pause:
                self.record(question=question, kind="checkbox", options=labels, probs=probs)
            if self.ask_human(f["question"]):
                return
        for o, p in zip(f["options"], probs):
            self.set_checked(o["sel"], p >= 0.5)
        checked = all(self.page.is_checked(o["sel"]) == (p >= 0.5) for o, p in zip(f["options"], probs))
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

    def click_forward(self):
        """Click Next/Continue. Returns False when finished or stopping at Submit."""
        buttons = self.page.locator("button, input[type=submit], input[type=button], [role=button]")
        for i in range(buttons.count()):
            b = buttons.nth(i)
            if not b.is_visible():
                continue
            label = (b.inner_text() or b.get_attribute("value") or b.get_attribute("aria-label") or "").strip()
            if NEXT_RE.search(label):
                b.click()
                return True
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
        fields = [f for f in fields if not is_control_group(f)]
        if not fields:
            return fields
        described = [f"{f['kind']} field. Question or label: {f['question'][:300]!r}."
                     + (f" Options: {[o['label'][:60] for o in f['options'][:8]]}." if f.get("options") else "")
                     + f" Nearby text: {f.get('context', '')!r}"
                     for f in fields]
        answers = self.ask({"page_title": self.page.title(), "page_fields": described}, {f"f{i}": {
            "type": "noul",
            "instructions": "Is this field part of the quiz or form the person came to fill in: one of its "
                            "questions, or a detail it asks about the person? Say no for site search, navigation, "
                            "language or translation, quiz settings, newsletter sign-up, login, comments, and buttons that "
                            "control the quiz, such as start, finish, retry, or share. "
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
        print(f" Q: {f['question'][:100]!r} [{f['kind']}]")
        if f["kind"] in ("radio", "select"):
            self.answer_single(f)
        elif f["kind"] == "checkbox":
            self.answer_checkboxes(f)
        else:
            self.answer_text(f)

    def run(self, max_pages=200):
        for step in range(1, max_pages + 1):
            self.page.wait_for_load_state("domcontentloaded")
            time.sleep(0.8)  # let single-page apps finish rendering
            fields = self.wait_for_fields()
            print(f"\n— Page {step}: {len(fields)} field(s)")
            self.dismiss_banners()
            # Some quizzes are one long page that reveals questions as you answer, so keep
            # checking for new ones until none appear. Answered fields are skipped by content.
            done, answered = set(), 0
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
                # A Next button here could lead anywhere, such as another quiz, so don't guess.
                print("\nFound no quiz questions on this page, so stopping here.")
                break
            if not self.click_forward():
                break
