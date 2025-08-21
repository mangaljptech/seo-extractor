import argparse
import csv
import json
import os
import html
import urllib.parse
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract SEO metadata and screenshots for a list of URLs using headless Chrome."
    )
    parser.add_argument(
        "--url",
        dest="urls",
        action="append",
        help="URL to scrape (can be passed multiple times)",
    )
    parser.add_argument(
        "--input",
        dest="input_file",
        help="Path to a text file containing one URL per line.",
    )
    parser.add_argument(
        "--output",
        dest="output_csv",
        default="/app/data/results.csv",
        help="CSV file to write results to (default: /app/data/results.csv)",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        default="/app/data/results.json",
        help="JSON file to write results to (default: /app/data/results.json)",
    )
    parser.add_argument(
        "--screenshots-dir",
        dest="screenshots_dir",
        default="/app/data/screenshots",
        help="Directory to save screenshots (default: /app/data/screenshots)",
    )
    parser.add_argument(
        "--meta-screenshots-dir",
        dest="meta_screenshots_dir",
        default="/app/data/screenshots_meta",
        help="Directory to save 'meta-only view' screenshots (default: /app/data/screenshots_meta)",
    )
    parser.add_argument(
        "--delay",
        dest="delay_seconds",
        type=float,
        default=2.0,
        help="Delay in seconds after page load before scraping (default: 2.0)",
    )
    parser.add_argument(
        "--remote",
        dest="remote_url",
        default=None,
        help="Optional Selenium Remote WebDriver URL (e.g., http://selenium:4444/wd/hub). If omitted, uses local Chrome/Chromedriver.",
    )
    return parser.parse_args()


def load_urls(args: argparse.Namespace) -> List[str]:
    urls: List[str] = []
    if args.urls:
        for item in args.urls:
            # Allow comma-separated values in a single --url argument
            parts = [u.strip() for u in item.split(",") if u.strip()]
            urls.extend(parts)
    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            for line in f:
                u = line.strip()
                if u:
                    urls.append(u)
    if not urls:
        urls = [
            "https://example.com",
            "https://www.python.org",
        ]
    return urls


def ensure_dirs(output_csv: str, output_json: str, screenshots_dir: str, meta_screenshots_dir: str) -> None:
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(screenshots_dir).mkdir(parents=True, exist_ok=True)
    Path(meta_screenshots_dir).mkdir(parents=True, exist_ok=True)


def create_webdriver(remote_url: str | None) -> webdriver.Chrome:
    options = Options()
    # Headless, Docker-friendly flags
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # If packaged with system chromium in Docker, this is the standard path
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    if os.path.exists(chrome_bin):
        options.binary_location = chrome_bin

    if remote_url:
        return webdriver.Remote(command_executor=remote_url, options=options)

    # Local driver path in our Docker image
    chromedriver_path = os.environ.get("CHROMEDRIVER", "/usr/bin/chromedriver")
    service = Service(executable_path=chromedriver_path)
    return webdriver.Chrome(service=service, options=options)


def sanitize_filename(url: str) -> str:
    # Remove protocol and non-filename-safe characters
    cleaned = re.sub(r"^https?://", "", url)
    cleaned = cleaned.replace("/", "_")
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", cleaned)
    return cleaned or "screenshot"


def extract_meta(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    def get_meta_by_name(name: str) -> str:
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content", "").strip() if tag else ""

    def get_meta_by_property(prop: str) -> str:
        tag = soup.find("meta", attrs={"property": prop})
        return tag.get("content", "").strip() if tag else ""

    def get_canonical() -> str:
        # rel can be a list or a string depending on parser normalization
        for link in soup.find_all("link"):
            rel = link.get("rel")
            if not rel:
                continue
            if isinstance(rel, list):
                rels = [r.lower() for r in rel]
                if "canonical" in rels:
                    return link.get("href", "").strip()
            else:
                if str(rel).lower() == "canonical":
                    return link.get("href", "").strip()
        return ""

    title_text = soup.title.string.strip() if soup.title and soup.title.string else ""

    return {
        "url": url,
        "title": title_text,
        "description": get_meta_by_name("description") or get_meta_by_property("og:description"),
        "keywords": get_meta_by_name("keywords"),
        "canonical": get_canonical(),
        "og:title": get_meta_by_property("og:title"),
        "og:url": get_meta_by_property("og:url"),
        "robots": get_meta_by_name("robots"),
    }


def collect_head_meta_markup(soup: BeautifulSoup) -> str:
    head = soup.head
    if not head:
        return ""
    lines: List[str] = []
    # Title first
    if head.title:
        lines.append(str(head.title))
    # Meta tags
    for tag in head.find_all("meta"):
        lines.append(str(tag))
    # Canonical and alternates
    for link in head.find_all("link"):
        rel = link.get("rel")
        if not rel:
            continue
        rels = [r.lower() for r in (rel if isinstance(rel, list) else [str(rel)])]
        if any(r in ("canonical", "alternate", "preload", "manifest", "icon") for r in rels):
            lines.append(str(link))
    return "\n".join(lines)


def build_meta_view_html(url: str, meta_markup: str) -> str:
    escaped = html.escape(meta_markup)
    doc = f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>Meta tags - {html.escape(url)}</title>
    <style>
      html, body {{ margin: 0; padding: 0; background: #0b0e14; }}
      body {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; color: #e6e1cf; }}
      header {{ padding: 16px 20px; border-bottom: 1px solid #1f2430; position: sticky; top: 0; background: #0b0e14; z-index: 1; }}
      h1 {{ font-size: 16px; margin: 0; color: #f0f0f0; }}
      main {{ padding: 16px 20px 40px; }}
      pre {{ white-space: pre-wrap; word-break: break-word; line-height: 1.4; }}
      code {{ color: #e6e1cf; }}
      .tag {{ color: #ffcc66; }}
      .attr {{ color: #5ccfe6; }}
      .val {{ color: #bae67e; }}
    </style>
  </head>
  <body>
    <header>
      <h1>Meta tags for {html.escape(url)}</h1>
    </header>
    <main>
      <pre><code>{escaped}</code></pre>
    </main>
  </body>
 </html>
"""
    return doc


def screenshot_meta_view(driver: webdriver.Chrome, url: str, soup: BeautifulSoup, out_dir: str) -> str:
    meta_markup = collect_head_meta_markup(soup)
    html_doc = build_meta_view_html(url, meta_markup)
    data_url = "data:text/html;charset=utf-8," + urllib.parse.quote(html_doc)
    driver.get(data_url)
    time.sleep(0.3)
    try:
        # Resize viewport height to fit content up to a reasonable max
        height = driver.execute_script(
            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, document.body.offsetHeight, document.documentElement.offsetHeight, document.body.clientHeight, document.documentElement.clientHeight);"
        )
        try:
            height_int = int(height)
        except Exception:
            height_int = 1200
        height_int = max(800, min(height_int + 100, 6000))
        driver.set_window_size(1920, height_int)
        time.sleep(0.1)
    except Exception:
        pass

    meta_filename = sanitize_filename(url) + "_meta.png"
    meta_path = str(Path(out_dir) / meta_filename)
    driver.save_screenshot(meta_path)
    return meta_path


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def main() -> int:
    args = parse_args()
    urls = load_urls(args)
    ensure_dirs(args.output_csv, args.output_json, args.screenshots_dir, args.meta_screenshots_dir)

    try:
        driver = create_webdriver(args.remote_url)
    except WebDriverException as e:
        print(f"Failed to initialize WebDriver: {e}", file=sys.stderr)
        return 2

    results: List[Dict[str, Any]] = []

    try:
        for url in urls:
            print(f"Processing: {url}")
            try:
                driver.get(url)
                time.sleep(args.delay_seconds)

                # Screenshot of rendered page
                filename = sanitize_filename(url) + ".png"
                screenshot_path = str(Path(args.screenshots_dir) / filename)
                driver.save_screenshot(screenshot_path)

                # Parse HTML
                soup = BeautifulSoup(driver.page_source, "html.parser")
                meta = extract_meta(soup, url)
                meta["screenshot"] = screenshot_path

                # Screenshot of meta-only view (simulated view-source focus on head/meta)
                try:
                    meta_view_path = screenshot_meta_view(driver, url, soup, args.meta_screenshots_dir)
                except Exception as meta_err:
                    meta_view_path = ""
                    print(f"Meta-view screenshot failed for {url}: {meta_err}", file=sys.stderr)
                meta["meta_screenshot"] = meta_view_path

                # Print a brief summary to stdout
                print(f"Title: {meta.get('title', '')}")
                print(f"Description: {meta.get('description', '')[:160]}")
                print(f"Canonical: {meta.get('canonical', '')}")
                print(f"Screenshot: {screenshot_path}")
                if meta.get("meta_screenshot"):
                    print(f"Meta screenshot: {meta['meta_screenshot']}")
                print("-" * 60)

                results.append(meta)
            except Exception as e:
                print(f"Error processing {url}: {e}", file=sys.stderr)
                failed_meta = {"url": url, "error": str(e), "screenshot": ""}
                results.append(failed_meta)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    write_csv(results, args.output_csv)
    write_json(results, args.output_json)
    print(f"Saved CSV: {args.output_csv}")
    print(f"Saved JSON: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


