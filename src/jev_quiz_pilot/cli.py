"""Command line: flags first, prompts for anything missing when run in a terminal."""
import argparse
import shlex
import sys
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from .banner import BANNER
from .jev import PROVIDERS, pick_provider

DEFAULT_ROLE = "You are an expert in the subject of this quiz. Pick the correct answer to each question."
DEFAULT_CDP_URL = "http://localhost:9222"


def parse_info(pairs):
    """Turn ["email=a@b.c", ...] into a dict. Keys name the fact, e.g. full_name or email."""
    info = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise argparse.ArgumentTypeError(f"--info needs KEY=VALUE, got {pair!r}")
        info[key.strip()] = value.strip()
    return info


def build_parser():
    p = argparse.ArgumentParser(
        prog="jev-quiz-pilot",
        description="Let Jev navigate a web quiz in your browser and pick the answers.")
    p.add_argument("url", nargs="?",
                   help="The quiz to open: a web address or a local HTML file. Leave out to be asked, "
                        "or to attach to your own Chrome with --cdp-url.")
    p.add_argument("--role", help="Who Jev acts as. Keep it short; unrelated text lowers accuracy.")
    p.add_argument("--info", action="append", default=[], metavar="KEY=VALUE",
                   help="A fact for identity fields, e.g. full_name='Jane Doe' or email=jane@example.com. Repeatable.")
    p.add_argument("--min-confidence", type=float, default=0.6,
                   help="Below this, pause so you answer (default: 0.6).")
    p.add_argument("--submit", action="store_true", help="Click the final Submit button. Off by default.")
    p.add_argument("--no-pause", action="store_true",
                   help="Never wait for you. On low confidence, use Jev's pick anyway.")
    p.add_argument("--provider", choices=["auto", *PROVIDERS], default="auto",
                   help="Where to send requests. auto uses whichever key is set, TypeSafe first (default: auto).")
    p.add_argument("-y", "--yes", action="store_true", help="Skip the setup prompts and use defaults.")
    p.add_argument("--cdp-url", metavar="URL",
                   help=f"Attach to your own Chrome instead of opening a new window, e.g. {DEFAULT_CDP_URL}. "
                        "Use this for quizzes that need your saved logins.")
    return p


def prompt(question, hint="Enter to skip"):
    return input(f"{question} ({hint}): ").strip()


def normalize_url(text):
    """Accept a local file, a bare domain, or a full URL."""
    if Path(text).is_file():
        return Path(text).resolve().as_uri()
    return text if "://" in text else "https://" + text


def fill_in_missing(args, info):
    """Ask for the quiz, role, and identity facts the flags didn't give."""
    print("A few questions first.\n")
    if args.url is None and args.cdp_url is None:
        url = prompt("Quiz URL", f"Enter to attach to your own Chrome at {DEFAULT_CDP_URL}")
        if url:
            args.url = normalize_url(url)
        else:
            args.cdp_url = DEFAULT_CDP_URL
    if args.role is None:
        print(f"Who should Jev act as? Default:\n  {DEFAULT_ROLE}")
        args.role = prompt("Role", "Enter for default") or None
    if not info:
        name = prompt("Your full name, for name fields")
        if name:
            info["full_name"] = name
        email = prompt("Your email, for email fields")
        if email:
            info["email"] = email
    print()


def name_parts(full_name):
    first, _, last = full_name.partition(" ")
    return {"first_name": first, "last_name": last} if last else {"first_name": first}


def rerun_command(args, info):
    cmd = ["jev-quiz-pilot"]
    if args.url:
        cmd.append(args.url)
    cmd.append("--yes")
    if args.role:
        cmd += ["--role", args.role]
    derived = name_parts(info["full_name"]) if "full_name" in info else {}
    for k, v in info.items():
        if derived.get(k) != v:  # skip first/last name that main() rebuilds from full_name
            cmd += ["--info", f"{k}={v}"]
    if args.min_confidence != 0.6:
        cmd += ["--min-confidence", str(args.min_confidence)]
    if args.submit:
        cmd.append("--submit")
    if args.no_pause:
        cmd.append("--no-pause")
    if args.provider != "auto":
        cmd += ["--provider", args.provider]
    if args.cdp_url:
        cmd += ["--cdp-url", args.cdp_url]
    return shlex.join(cmd)


def launch(p):
    """Open a visible browser: your installed Chrome if there is one, else Playwright's Chromium."""
    for channel in ("chrome", None):
        try:
            return p.chromium.launch(channel=channel, headless=False, args=["--window-size=1280,900"])
        except Exception:
            continue
    sys.exit("Can't start a browser. Install Google Chrome, or run: uv run playwright install chromium")


def open_quiz(p, args, interactive):
    """Return (page, browser we own or None). Opens the URL in a new window, or attaches to your Chrome."""
    if args.url:
        browser = launch(p)
        page = browser.new_context(no_viewport=True).new_page()
        page.goto(args.url, wait_until="domcontentloaded")  # ad-heavy pages may never finish loading
        if interactive:
            input("Log in or go to the first question if needed, then press Enter to start… ")
        return page.context.pages[-1], browser
    cdp_url = args.cdp_url or DEFAULT_CDP_URL
    try:
        browser = p.chromium.connect_over_cdp(cdp_url)
    except Exception:
        sys.exit(f"Can't reach Chrome at {cdp_url}.\n"
                 f"Pass the quiz URL instead:  jev-quiz-pilot https://example.com/quiz\n"
                 f"Or start Chrome with remote debugging; see the README.")
    return browser.contexts[0].pages[-1], None  # the most recently opened tab


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        info = parse_info(args.info)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    if sys.stdout.isatty():
        print(BANNER)

    load_dotenv(find_dotenv(usecwd=True))  # reads the API keys from .env in the folder you run from
    try:
        provider = pick_provider(args.provider)
    except ValueError as e:
        sys.exit(str(e))

    if args.url and args.cdp_url:
        parser.error("pass a quiz URL or --cdp-url, not both")
    if args.url:
        args.url = normalize_url(args.url)
    interactive = sys.stdin.isatty() and not args.yes
    try:
        if interactive:
            fill_in_missing(args, info)
            print(f"Rerun with:\n  {rerun_command(args, info)}\n")
        if "full_name" in info:
            info = {**name_parts(info["full_name"]), **info}  # flags win over the split
        role = args.role or DEFAULT_ROLE

        # Imported here so --help and the prompts stay fast.
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        from .runner import Session

        log_path = Path("runs") / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        log_path.parent.mkdir(exist_ok=True)

        with sync_playwright() as p:
            page, own_browser = open_quiz(p, args, interactive)
            print(f"Controlling: {page.title()}  ({page.url})")
            print(f"Provider: {provider.name} ({provider.key_env}, model {provider.model})")
            print(f"Role: {role}\nLog: {log_path}")
            try:
                Session(page, provider, role, log_path, info=info, min_confidence=args.min_confidence,
                        submit=args.submit, pause=not args.no_pause).run()
            except PlaywrightError as e:
                sys.exit(f"\nLost the browser page: {e.message.splitlines()[0]}")
            if own_browser and sys.stdin.isatty():
                # Closing the window would throw away the answers before you review or submit them.
                input("\nPress Enter to close the browser… ")
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
        sys.exit(130)


if __name__ == "__main__":
    main()
