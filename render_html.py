"""
Blitz Culture — HTML to PNG renderer
---------------------------------------
SETUP (one-time):
  pip install playwright
  playwright install chromium
"""

from playwright.sync_api import sync_playwright


def render_html_to_png(html: str, output_path: str, width: int = 1080, height: int = 1350):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html)
        page.screenshot(path=output_path)
        browser.close()
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    # Quick smoke test using one of the guided templates
    from html_templates import ranking_card_clean_list
    import os

    html = ranking_card_clean_list(
        "Top 5 WR - Week 1",
        [
            {"label": "1. Ja'Marr Chase", "value": "WR - CIN"},
            {"label": "2. CeeDee Lamb", "value": "WR - DAL"},
            {"label": "3. Justin Jefferson", "value": "WR - MIN"},
        ],
    )
    os.makedirs("output", exist_ok=True)
    render_html_to_png(html, "output/test_render.png")
