"""Render docs/hero.png from the CLI banner. Run: uv run python docs/render_hero.py docs/hero.png"""
import html, sys
from playwright.sync_api import sync_playwright
from jev_quiz_pilot.banner import BANNER

art = html.escape(BANNER.strip("\n"))
page_html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin:0; background:transparent; }}
  .win {{ display:inline-block; margin:24px; background:#0d1117; border-radius:12px;
          box-shadow:0 12px 40px rgba(0,0,0,.35); border:1px solid #30363d; overflow:hidden; }}
  .bar {{ height:36px; background:#161b22; display:flex; align-items:center; gap:8px; padding:0 14px;
          border-bottom:1px solid #30363d; }}
  .dot {{ width:12px; height:12px; border-radius:50%; }}
  .body {{ padding:22px 32px 26px; font-family: Menlo, "SF Mono", monospace; font-size:15px; line-height:1.18; color:#e6edf3; }}
  pre {{ margin:0; font:inherit; }}
  .cmd {{ color:#8b949e; margin-bottom:14px; }} .cmd b {{ color:#3fb950; font-weight:normal; }}
  .art {{ color:#58a6ff; line-height:1.0; }}
  .tag {{ margin-top:16px; color:#8b949e; }}
</style></head><body><div class="win">
  <div class="bar"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27c93f"></span></div>
  <div class="body">
    <pre class="cmd"><b>$</b> uv run jev-quiz-pilot</pre>
    <pre class="art">{art}</pre>
    <pre class="tag">Jev navigates a web quiz in your Chrome and picks the answers.</pre>
  </div></div></body></html>"""

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(device_scale_factor=2)
    pg.set_content(page_html)
    pg.locator(".win").screenshot(path=sys.argv[1], omit_background=True)
    b.close()
