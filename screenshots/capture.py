"""Take the screenshots used in the README and the documentation.

    pip install playwright                       # uses your installed Chrome, nothing to download
    biobank-local --root /tmp/shots setup --non-interactive --admin-password 'screenshots-1' --demo
    biobank-local --root /tmp/shots run --port 8765 &
    python docs/screenshots/capture.py http://127.0.0.1:8765

Images are written to docs/screenshots/. The demo lab is fictional.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765").rstrip("/")
OUT = Path(__file__).resolve().parent

# (file name, path, optional action run after the page loads)
PAGES = [
    ("home", "/workspace/", None),
    ("samples", "/samples/", None),
    ("sample-detail", "/samples/1/", None),
    ("sample-new", "/samples/add/", "storage"),
    ("storage", "/storage/", "box"),
    ("import", "/samples/import/", None),
    ("notebook", "/internal/lab-tools/notebook/entries/", None),
    ("notebook-entry", "/internal/lab-tools/notebook/entry/1/", None),
    ("molecular-registry", "/internal/lab-tools/molecular-registry/", None),
    ("molecular-record", "/internal/lab-tools/molecular-registry/1/", None),
    ("calendar", "/calendar/", None),
    ("history", "/calendar/history/", None),
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1).new_page()
        page.goto(f"{BASE}/login/")
        page.fill("input[name=username]", "demo")
        page.fill("input[name=password]", "demo-password-123")
        page.click("button[type=submit], input[type=submit]")
        page.wait_for_load_state("networkidle")

        for name, path, action in PAGES:
            page.goto(BASE + path)
            page.wait_for_load_state("networkidle")

            if action == "box":
                page.get_by_text("Box 1", exact=True).first.click()
                page.wait_for_timeout(800)

            if action == "storage":
                page.wait_for_selector("#storageChildWorkspaceV8146 option[value]", state="attached")
                page.select_option("#storageChildWorkspaceV8146", label="Demo Lab")
                box = page.locator("#storageInputVisual")

                for level in ("Freezer -80 A", "Rack 1", "Box 4", "B3"):
                    box.fill(level)
                    box.press("Enter")

                page.select_option("#storageChildOrgV8146", "grid")
                page.evaluate("document.getElementById('b3s-unified-storage-card')?.scrollIntoView()")

            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("saved", name)

        browser.close()


if __name__ == "__main__":
    main()
