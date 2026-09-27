"""Command line: flags first, prompts for anything missing when run in a terminal."""
import argparse
import os
import shlex
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .banner import BANNER

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
        description="Let Jev navigate a web quiz in your Chrome and pick the answers.")
    p.add_argument("--role", help="Who Jev acts as. Keep it short; unrelated text lowers accuracy.")
    p.add_argument("--info", action="append", default=[], metavar="KEY=VALUE",
                   help="A fact for identity fields, e.g. full_name='Jane Doe' or email=jane@example.com. Repeatable.")
    p.add_argument("--min-confidence", type=float, default=0.6,
                   help="Below this, pause so you answer (default: 0.6).")
    p.add_argument("--submit", action="store_true", help="Click the final Submit button. Off by default.")
    p.add_argument("--no-pause", action="store_true",
                   help="Never wait for you. On low confidence, use Jev's pick anyway.")
    p.add_argument("-y", "--yes", action="store_true", help="Skip the setup prompts and use defaults.")
    p.add_argument("--cdp-url", default=DEFAULT_CDP_URL, help=f"Chrome debugging address (default: {DEFAULT_CDP_URL}).")
    return p


def prompt(question, hint="Enter to skip"):
    return input(f"{question} ({hint}): ").strip()


def fill_in_missing(args, info):
    """Ask for the role and identity facts the flags didn't give."""
    print("A few questions first.\n")
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
    cmd = ["jev-quiz-pilot", "--yes"]
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
    if args.cdp_url != DEFAULT_CDP_URL:
        cmd += ["--cdp-url", args.cdp_url]
    return shlex.join(cmd)


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        info = parse_info(args.info)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    if sys.stdout.isatty():
        print(BANNER)

    load_dotenv()  # reads OPENROUTER_API_KEY from .env
    if not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY is not set. Put it in .env or export it. See .env.example.")

    try:
        if sys.stdin.isatty() and not args.yes:
            fill_in_missing(args, info)
            print(f"Rerun with:\n  {rerun_command(args, info)}\n")
        if "full_name" in info:
            info = {**name_parts(info["full_name"]), **info}  # flags win over the split
        role = args.role or DEFAULT_ROLE

        # Imported here so --help and the prompts stay fast.
        from playwright.sync_api import sync_playwright

        from .runner import Session

        log_path = Path("runs") / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        log_path.parent.mkdir(exist_ok=True)

        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(args.cdp_url)
            except Exception:
                sys.exit(f"Can't reach Chrome at {args.cdp_url}. Start it with remote debugging; see the README.")
            page = browser.contexts[0].pages[-1]  # the most recently opened tab
            print(f"Controlling: {page.title()}  ({page.url})")
            print(f"Role: {role}\nLog: {log_path}")
            Session(page, role, log_path, info=info, min_confidence=args.min_confidence,
                    submit=args.submit, pause=not args.no_pause).run()
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
        sys.exit(130)


if __name__ == "__main__":
    main()
