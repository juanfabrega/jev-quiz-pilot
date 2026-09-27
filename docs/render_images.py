"""Render the README hero and the GitHub social preview from the CLI banner.

Run: uv run python docs/render_images.py
Writes docs/hero.png and docs/social-preview.png.
"""
import html
from pathlib import Path

from playwright.sync_api import sync_playwright

from jev_quiz_pilot.banner import BANNER

DOCS = Path(__file__).parent
ART = html.escape(BANNER.strip("\n"))
TAGLINE = "Jev navigates a web quiz in your Chrome and picks the answers."

STYLE = """
  body { margin:0; background:transparent; font-family: Menlo, "DejaVu Sans Mono", monospace; }
  pre { margin:0; font:inherit; }
  .art { color:#58a6ff; line-height:1.0; }
  .muted { color:#8b949e; }
  .win { display:inline-block; margin:24px; background:#0d1117; border-radius:12px;
         border:1px solid #30363d; overflow:hidden; }
  .bar { height:36px; background:#161b22; display:flex; align-items:center; gap:8px; padding:0 14px;
         border-bottom:1px solid #30363d; }
  .dot { width:12px; height:12px; border-radius:50%; }
  .body { padding:22px 32px 26px; font-size:15px; line-height:1.18; color:#e6edf3; }
  .cmd { margin-bottom:14px; } .cmd b { color:#3fb950; font-weight:normal; }
  .tag { margin-top:16px; }
  .social { width:1280px; height:640px; background:#0d1117; display:flex; flex-direction:column;
            align-items:center; justify-content:center; gap:36px; }
  .social .art { font-size:23px; }
  .social .tag { font-size:26px; color:#e6edf3; margin:0; }
  .social .sub { font-size:20px; }
"""

HERO = f"""<div class="win">
  <div class="bar"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27c93f"></span></div>
  <div class="body">
    <pre class="cmd muted"><b>$</b> uv run jev-quiz-pilot</pre>
    <pre class="art">{ART}</pre>
    <pre class="tag muted">{TAGLINE}</pre>
  </div></div>"""

SOCIAL = f"""<div class="social">
  <pre class="art">{ART}</pre>
  <pre class="tag">{TAGLINE}</pre>
  <pre class="sub muted">Python CLI · TypeSafe or OpenRouter · Playwright</pre>
</div>"""


def render(page, body, selector, path):
    page.set_content(f'<!doctype html><html><head><meta charset="utf-8"><style>{STYLE}</style></head><body>{body}</body></html>')
    page.locator(selector).screenshot(path=path, omit_background=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    render(browser.new_page(device_scale_factor=2), HERO, ".win", DOCS / "hero.png")
    render(browser.new_page(), SOCIAL, ".social", DOCS / "social-preview.png")  # GitHub wants exactly 1280x640
    browser.close()
