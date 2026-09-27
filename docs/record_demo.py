"""Record docs/demo.gif: Jev takes docs/demo/index.html, with the CLI output shown in a panel beside the quiz.

Uses the same Session code as the CLI, in a browser Playwright records. Needs an API key in .env and ffmpeg.
Run: uv run python docs/record_demo.py
"""
import html
import subprocess
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from jev_quiz_pilot import runner
from jev_quiz_pilot.jev import pick_provider

DOCS = Path(__file__).parent
QUIZ = (DOCS / "demo" / "index.html").resolve().as_uri()
ROLE = "You are a trivia champion. Pick the correct answer to each question."
INFO = {"full_name": "Ada Lovelace", "first_name": "Ada", "last_name": "Lovelace"}
SIZE = {"width": 1280, "height": 760}

PANEL = """
<style>
  main { margin-left:32px !important; max-width:680px !important; }
  #jev-panel { position:fixed; top:0; right:0; bottom:0; width:520px; background:#0d1117; color:#e6edf3;
    font:13px/1.55 Menlo, "DejaVu Sans Mono", monospace; padding:18px 20px; overflow:hidden; z-index:9;
    border-left:1px solid #30363d; }
  #jev-panel .title { color:#58a6ff; font-weight:bold; margin-bottom:4px; }
  #jev-panel .cmd { color:#8b949e; margin-bottom:12px; word-break:break-all; }
  #jev-panel .cmd b { color:#3fb950; font-weight:normal; }
  #jev-panel div.l { white-space:pre-wrap; word-break:break-word; }
  #jev-panel .page { color:#d2a8ff; margin-top:10px; } #jev-panel .q { color:#e6edf3; }
  #jev-panel .pick { color:#3fb950; } #jev-panel .warn { color:#d29922; } #jev-panel .off { color:#6e7681; }
</style>
<div id="jev-panel">
  <div class="title">JEV QUIZ PILOT</div>
  <div class="cmd"><b>$</b> jev-quiz-pilot --yes --submit --no-pause --info 'full_name=Ada Lovelace' --role 'You are a trivia champion. …'</div>
  <div id="jev-lines"></div>
</div>
"""

ADD_LINE = """([text, cls]) => {
  const box = document.getElementById('jev-lines');
  const d = document.createElement('div'); d.className = 'l ' + cls; d.textContent = text; box.append(d);
  while (box.scrollHeight > box.parentElement.clientHeight - 90) box.firstChild.remove();
}"""


def line_class(text):
    t = text.strip()
    if t.startswith("—"): return "page"
    if t.startswith("Q:"): return "q"
    if t.startswith(("→", "☑")): return "pick"
    if t.startswith(("⚠", "✋")): return "warn"
    return "off"


def main():
    load_dotenv()
    provider = pick_provider()
    out_dir = DOCS / ".recording"
    log_path = Path("runs") / f"demo-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    log_path.parent.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(slow_mo=250)
        context = browser.new_context(viewport=SIZE, record_video_dir=out_dir, record_video_size=SIZE)
        page = context.new_page()
        page.goto(QUIZ)
        page.evaluate("h => document.body.insertAdjacentHTML('beforeend', h)", PANEL)

        def show(*args, **_):
            text = " ".join(str(a) for a in args)
            print(text)
            for part in text.strip("\n").split("\n"):
                if part.strip():
                    page.evaluate(ADD_LINE, [part.strip(), line_class(part)])
                    time.sleep(0.35)  # give viewers time to read

        runner.print = show  # route the Session's output into the panel as well as the terminal
        time.sleep(1)
        runner.Session(page, provider, ROLE, log_path, info=INFO, submit=True, pause=False).run()
        show("\nDone. Results are on the page.")
        time.sleep(4)  # hold on the score
        video = page.video.path()
        context.close()
        browser.close()

    gif = DOCS / "demo.gif"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-ss", "0.6", "-i", str(video),
        "-vf", "fps=10,scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];"
               "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
        "-loop", "0", str(gif),
    ], check=True)
    Path(video).unlink()
    out_dir.rmdir()
    print(f"Wrote {gif} ({gif.stat().st_size / 1e6:.1f} MB). Log: {log_path}")


if __name__ == "__main__":
    main()
