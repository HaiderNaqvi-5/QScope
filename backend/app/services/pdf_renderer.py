"""Isolated PDF renderer entry point.

Playwright owns helper processes and event-loop resources. Running it in a short-lived
child process prevents one failed render from contaminating the desktop backend loop.
"""
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    source, destination = map(Path, sys.argv[1:])
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(source.resolve().as_uri(), wait_until="load")
            page.pdf(path=str(destination), format="A4", print_background=True)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
