"""
Jev navigates a web quiz in your Chrome.

Jev doesn't generate text or see screenshots. This module is its eyes and hands:
it reads each question and its options from the page, asks Jev to pick, and clicks.
Every decision goes to runs/<timestamp>.jsonl so you can score it later.
"""
import json
import re
import time
from pathlib import Path

import requests

from .jev import decide

EXTRACT_JS = (Path(__file__).parent / "extract.js").read_text()

NEXT_RE = re.compile(r"^\s*(next|continue|forward|proceed|save (and|&) (next|continue)|submit answer|›|>|→)", re.I)
SUBMIT_RE = re.compile(r"^\s*(submit|finish|done|send|complete|end (test|exam|assessment|quiz))", re.I)


class Session:
    def __init__(self, page, role, log_path, info=None, min_confidence=0.6, submit=False, pause=True):
        self.page = page
        self.role = role
        self.info = info or {}
        self.min_confidence = min_confidence
        self.submit = submit
        self.pause = pause
        self.log = log_path.open("a")

    def record(self, **entry):
        self.log.write(json.dumps(entry) + "\n")
        self.log.flush()

    def ask(self, state, questions):
        """Call Jev. Returns None on a network or API error, so the caller can hand off to you."""
        try:
            return decide(state, questions)
        except (requests.RequestException, KeyError, ValueError) as e:
            print(f"   ⚠ Jev request failed: {e}")
            return None

    def set_checked(self, sel, on=True):
        """Tick or untick. force=True clicks through custom-styled labels that cover the input."""
        (self.page.check if on else self.page.uncheck)(sel, force=True)

    def ask_human(self, question, reason="Not confident"):
        """Returns True if you answered; False means carry on without you."""
        if not self.pause:
            print(f"   ⚠ {reason}, not pausing (--no-pause)")
            return False
        self.record(question=question, answered_by="human", reason=reason)
        input(f"   ⚠ {reason} on: {question!r}\n   Answer it yourself in the browser, then press Enter… ")
        return True

    def answer_single(self, f):
        """Radio group or dropdown: one Choice question over the visible options."""
        labels = [o["label"] or f"option {i}" for i, o in enumerate(f["options"])]
        criteria = {f"opt{i}": label for i, label in enumerate(labels)}
        state = {"role": self.role, "assessment_question": f["question"]}
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
        self.record(question=f["question"], kind=f["kind"], options=labels,
                    choice=labels[idx], confidence=a["confidence"])
        if a["confidence"] < self.min_confidence and self.ask_human(f["question"]):
            return
        if f["kind"] == "select":
            self.page.select_option(f["sel"], f["options"][idx]["value"])
        else:
            self.set_checked(f["options"][idx]["sel"])

    def answer_checkboxes(self, f):
        """Select-all-that-apply: one Noul per option, all in a single parallel request.

        Each question can't see the others, so the full option list goes in the state.
        """
        labels = [o["label"] for o in f["options"]]
        state = {"role": self.role, "assessment_question": f["question"], "all_options": labels}
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
        self.record(question=f["question"], kind="checkbox", options=labels, probs=probs)
        if any(0.35 < p < 0.65 for p in probs) and self.ask_human(f["question"]):
            return
        for o, p in zip(f["options"], probs):
            self.set_checked(o["sel"], p >= 0.5)

    def answer_text(self, f):
        """Text box: fill identity fields from your info. Open-ended answers go to you."""
        if f.get("filled"):
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
        print("\nNo Next/Submit button found. Stopping.")
        return False

    def run(self, max_pages=200):
        for step in range(1, max_pages + 1):
            self.page.wait_for_load_state("domcontentloaded")
            time.sleep(0.8)  # let single-page apps finish rendering
            fields = self.page.evaluate(EXTRACT_JS)
            print(f"\n— Page {step}: {len(fields)} field(s)")
            for f in fields:
                print(f" Q: {f['question'][:100]!r} [{f['kind']}]")
                if f["kind"] in ("radio", "select"):
                    self.answer_single(f)
                elif f["kind"] == "checkbox":
                    self.answer_checkboxes(f)
                else:
                    self.answer_text(f)
            if not self.click_forward():
                break
