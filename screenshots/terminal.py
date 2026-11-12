"""Render the install wizard as an image for the README (the text is what `biobank-local setup` prints)."""

from pathlib import Path

from playwright.sync_api import sync_playwright

TEXT = """$ pipx install "git+https://github.com/leepusp/b3lims.git"
$ biobank-local setup

  ____  _____   _     ___ __  __ ____
 | __ )|___ /  | |   |_ _|  \\/  / ___|
 |  _ \\  |_ \\  | |    | || |\\/| \\___ \\
 | |_) |___) | | |___ | || |  | |___) |
 |____/|____/  |_____|___|_|  |_|____/
  B3 LIMS  v0.1.0  -  Samples, freezers, notebooks and shipments for research labs.

Setup
=====
Step 1 of 4  Where should your data live?
Data folder [/home/ana/.biobank-local]:

Step 2 of 4  Database
  1) SQLite  (one file, nothing to install; best for one person or a small lab)
  2) PostgreSQL  (for a lab server shared by many people)
Choose 1 or 2 [1]:

Step 3 of 4  Administrator account
Username [admin]: ana
E-mail (optional): ana@lab.example
Password (at least 8 characters): ************

Step 4 of 4  Network
Will other computers open this installation (not only this one)? [y/N]: n
Time zone [UTC]: America/Sao_Paulo

Writing settings to /home/ana/.biobank-local/config.env
Creating the database ...
Preparing the web files ...
Created administrator 'ana'.

Done. Start B3 LIMS with:

    biobank-local run

then open http://127.0.0.1:8000/ and sign in as 'ana'.

$ biobank-local run
B3 LIMS is running at http://127.0.0.1:8000/  (Ctrl+C to stop)"""

HTML = """<html><body style="margin:0;background:#0d1b2a;">
<div style="padding:22px 26px;font:15px/1.5 'DejaVu Sans Mono',Menlo,monospace;color:#d6e2f0;width:880px">
<div style="margin-bottom:12px"><span style="color:#ff5f56">&#9679;</span> <span style="color:#ffbd2e">&#9679;</span> <span style="color:#27c93f">&#9679;</span></div>
<pre style="margin:0;white-space:pre-wrap">__TEXT__</pre></div></body></html>"""


def main():
    import html

    body = html.escape(TEXT).replace("$ ", '<span style="color:#7ee787">$</span> ')
    page_html = HTML.replace("__TEXT__", body)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 930, "height": 400})
        page.set_content(page_html)
        page.locator("div").first.screenshot(path=str(Path(__file__).resolve().parent / "install-wizard.png"))
        browser.close()


if __name__ == "__main__":
    main()
