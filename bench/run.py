"""Run the harness on real quiz pages and score how well it navigates them. Jev's accuracy is not scored.

  uv run python bench/run.py                    # every case, 4 at a time
  uv run python bench/run.py funtrivia demo     # some cases
  uv run python bench/run.py --fake-answers         # answers skip Jev: always the last option
  uv run python bench/run.py --record           # save a snapshot of each page for later replays

A case replays from bench/snapshots/ when a snapshot exists, else it loads the live site.
Snapshots and results hold third-party page content, so they stay out of git.
Uses a visible Chrome window: bot walls such as Cloudflare block headless Chrome.
"""
import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from cases import CASES  # noqa: E402

# Reads each question and its options with the case's own selectors.
TRUTH_JS = """(c) => {
  const txt = e => (e.innerText || '').replace(/\\s+/g, ' ').trim();
  window.__benchIds = window.__benchIds || 0;
  return [...document.querySelectorAll(c.block)].filter(b => b.getClientRects().length).map(b => {
    b.dataset.benchId = b.dataset.benchId || performance.timeOrigin + '#' + window.__benchIds++;  // unique per page load
    const options = [...b.querySelectorAll(c.option)].map(txt).filter(Boolean);
    let question;
    if (c.question) question = txt(b.querySelector(c.question));
    else {
      const copy = b.cloneNode(true);
      copy.querySelectorAll(c.option + (c.exclude ? ',' + c.exclude : '')).forEach(e => e.remove());
      document.body.append(copy);  // innerText needs the copy in the page
      question = txt(copy);
      copy.remove();
    }
    return {id: b.dataset.benchId, question, options};
  }).filter(q => q.question && q.options.length);
}"""


def norm(s):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", s).lower())  # NFKC: math 𝑥 becomes x


def same_options(got, want):
    """Same count, and each option close to one of the page's. Loose, since formulas read differently
    before and after MathJax draws them."""
    got, want = sorted(map(norm, got)), sorted(map(norm, want))
    return len(got) == len(want) and all(
        any(g in w or w in g or SequenceMatcher(None, g, w).ratio() >= 0.75 for w in want) for g in got)


def score(case, truth, decisions, output, final_url, error):
    """Compare what the harness did with what the page really holds."""
    matched, stray = {}, []
    for d in decisions:
        # Fuzzy, since the page's raw text can differ from the harness's cleaned text, e.g. in formulas.
        # A question read as one of its options scores far below the cutoff.
        nd = norm(d["question"])[:200]
        ratios = {k: SequenceMatcher(None, norm(k)[:200], nd).ratio() for k in truth}
        key = max(ratios, key=ratios.get, default=None)
        if key is None or ratios[key] < 0.6:
            stray.append(d["question"][:80])
        else:
            matched.setdefault(key, d)
    total = case.get("total", len(truth))
    clean = [k for k, d in matched.items() if len(norm(d["question"])) <= 1.3 * len(norm(k)) + 30]
    options = [k for k, d in matched.items() if same_options(d["options"], truth[k])]
    checked = [k for k, d in matched.items() if d.get("checked")]
    end_ok = case.get("end") != "submit" or "Reached Submit" in output
    stay_ok = not case.get("stay") or final_url.startswith(case["stay"])
    r = dict(total=total, seen=len(truth), found=len(matched), clean=len(clean), options=len(options),
             checked=len(checked), stray=len(stray), end_ok=end_ok, stay_ok=stay_ok, error=error,
             stray_examples=stray[:5],
             missed=[k[:80] for k in truth if k not in matched][:5],
             unclean=[matched[k]["question"][:120] for k in matched if k not in clean][:3],
             option_diffs=[(matched[k]["options"], truth[k]) for k in matched if k not in options][:3])
    r["pass"] = (not error and stay_ok and end_ok and r["stray"] == 0
                 and r["found"] == r["clean"] == r["options"] == r["checked"] == total)
    return r


def run_one(name, out_dir, fake_answers, record):
    """Runs in a child process. Writes <name>.json with the score."""
    from dotenv import load_dotenv
    from playwright.sync_api import sync_playwright

    from jev_quiz_pilot import runner
    from jev_quiz_pilot.jev import pick_provider

    case = CASES[name]
    load_dotenv(ROOT / ".env")
    provider = pick_provider()
    if fake_answers:
        real = runner.decide

        def fake(provider, state, questions):
            """Answer picks skip the API: always the last option, or yes. The harness's own questions,
            such as which text is the question, still go to Jev, since they are part of what we test."""
            if "assessment_question" not in state:
                return real(provider, state, questions)
            return {k: {"choice": list(q["criteria"])[-1], "confidence": 0.9} if q["type"] == "choice"
                    else {"noul": 0.9} for k, q in questions.items()}
        runner.decide = fake

    truth = {}

    class Scored(runner.Session):
        """Reads the true questions on every page, and before each answer for pages that load more."""
        def look(self):
            if case.get("block"):
                try:
                    for q in self.page.evaluate(TRUTH_JS, case):
                        truth[q["id"]] = q  # keyed by element: text can change as the page finishes drawing
                except Exception:
                    pass  # page mid-navigation

        def wait_for_fields(self, timeout=10):
            fields = super().wait_for_fields(timeout)
            self.look()
            return fields

        def answer(self, f):
            self.look()
            super().answer(f)

    snapshot = HERE / "snapshots" / f"{name}.zip"
    log = out_dir / f"{name}.jsonl"
    error, final_url, t0 = None, "", time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False, args=["--window-size=1280,900"])
        if record and not case.get("live"):
            snapshot.parent.mkdir(exist_ok=True)
            ctx = browser.new_context(no_viewport=True, record_har_path=snapshot, record_har_content="attach")
        else:
            ctx = browser.new_context(no_viewport=True)
            if snapshot.exists() and not case.get("live"):
                ctx.route_from_har(snapshot, not_found="abort")
        page = ctx.new_page()
        try:
            page.goto(case["url"], wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            for text in case.get("start", []):
                page.get_by_text(text).first.click(timeout=10000)
                time.sleep(2)
            session = Scored(page, provider, "You are an expert. Pick the correct answer.", log,
                             pause=False, submit=False)
            session.run(max_pages=40)
            session.look()
        except Exception as e:
            error = f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
            print("ERROR:", error)
        final_url = page.url
        page.goto("about:blank")  # ads keep requests open, and a recording waits for them on close
        ctx.close()  # writes the snapshot when recording
        browser.close()
    decisions = [d for d in map(json.loads, log.read_text().splitlines()) if "options" in d] if log.exists() else []
    output = (out_dir / f"{name}.log").read_text()
    truth = {q["question"]: q["options"] for q in truth.values()}
    result = score(case, truth, decisions, output, final_url, error)
    result.update(name=name, seconds=round(time.time() - t0), replay=snapshot.exists() and not record)
    (out_dir / f"{name}.json").write_text(json.dumps(result, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cases", nargs="*", help="Case names. Default: all.")
    ap.add_argument("--fake-answers", action="store_true", help="Don't ask Jev for answers; always pick the last option. Cheaper and repeatable.")
    ap.add_argument("--record", action="store_true", help="Load the live site and save a snapshot for replays.")
    ap.add_argument("--jobs", type=int, default=4, help="Cases to run at once (default 4).")
    ap.add_argument("--one", help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.one:
        run_one(args.one, Path(args.out), args.fake_answers, args.record)
        return

    names = args.cases or list(CASES)
    unknown = set(names) - set(CASES)
    if unknown:
        sys.exit(f"Unknown case: {', '.join(sorted(unknown))}. Known: {', '.join(CASES)}")
    out = HERE / "results" / f"{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True)

    def child(name):
        cmd = [sys.executable, "-u", __file__, "--one", name, "--out", str(out)]
        cmd += ["--fake-answers"] * args.fake_answers + ["--record"] * args.record
        with (out / f"{name}.log").open("w") as f:
            try:
                subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=600, cwd=out)
            except subprocess.TimeoutExpired:
                pass
        path = out / f"{name}.json"
        return json.loads(path.read_text()) if path.exists() else {"name": name, "pass": False, "error": "no result (timed out or crashed)"}

    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(child, names))

    cols = ["found", "clean", "options", "checked"]
    print(f"\n{'case':24} {'pass':5} {'total':>5} {'seen':>5} " + " ".join(f"{c:>7}" for c in cols)
          + f" {'stray':>5} {'end':>4} {'stay':>4} {'secs':>5}")
    for r in results:
        if "total" not in r:
            print(f"{r['name']:24} {'FAIL':5} {r['error']}")
            continue
        print(f"{r['name']:24} {'ok' if r['pass'] else 'FAIL':5} {r['total']:>5} {r['seen']:>5} "
              + " ".join(f"{r[c]:>7}" for c in cols)
              + f" {r['stray']:>5} {'ok' if r['end_ok'] else 'no':>4} {'ok' if r['stay_ok'] else 'no':>4}"
              + f" {r['seconds']:>5}" + (f"  {r['error']}" if r["error"] else ""))
    passed = sum(r["pass"] for r in results)
    print(f"\n{passed}/{len(results)} cases pass. Details: {out}")
    (out / "summary.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
