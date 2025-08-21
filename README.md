## SEO Extractor (Selenium + BeautifulSoup)

This project extracts SEO metadata and screenshots from a list of URLs using headless Chromium driven by Selenium, all inside Docker.

### What it collects

- **title**
- **meta description** (name="description" or og:description)
- **keywords** (if present)
- **canonical URL**
- **Open Graph**: og:title, og:url
- **robots**
- **screenshot** of the page (1920x1080)

### Prerequisites

- Docker and Docker Compose installed

### Quick start

1. Creata and put your URLs (one per line) into `urls.txt`.
2. Build and run with Docker Compose:

```bash
cd /Users/mangallimbumangallimbu/Development/diamondicq/seo-extractor
docker compose build
docker compose up --remove-orphans
```

3. Results will be saved to:

- CSV: `data/results.csv`
- JSON: `data/results.json`
- Screenshots: `data/screenshots/*.png`
- Meta-only screenshots (head/meta focus): `data/screenshots_meta/*.png`

### Run options

The container entrypoint is `python /app/scrape_seo.py`. You can override CLI options via Compose or `docker run`.

Available flags:

- `--input /path/to/urls.txt` (one URL per line)
- `--url https://site1.com --url https://site2.com` (can be repeated or comma-separated)
- `--output /app/data/results.csv` (CSV output path)
- `--json /app/data/results.json` (JSON output path)
- `--screenshots-dir /app/data/screenshots`
- `--meta-screenshots-dir /app/data/screenshots_meta`
- `--delay 2.0` (seconds to wait after navigation)
- `--remote http://selenium:4444/wd/hub` (use remote Selenium instead of local Chromium)

Examples:

```bash
# Use the urls.txt file mounted by compose
docker compose run --rm seo-scraper --input /app/urls.txt --delay 1.5

# Pass inline URLs and change output names
docker compose run --rm seo-scraper \
  --url https://example.com,https://www.python.org \
  --output /app/data/seo.csv \
  --json /app/data/seo.json
```

### Local output

Compose mounts the host `./data` directory to `/app/data` in the container, so your outputs persist to your filesystem.

### Notes

- The image installs Debian `chromium` and `chromium-driver` and configures Selenium to use them. No external browsers are needed.
- If you run this on Apple Silicon, Docker’s linux/arm64 base image works fine; Debian’s chromium packages support arm64.
- Some sites block headless browsers or require more wait time. Increase `--delay` if content is loaded via JavaScript.

### Development

If you want to run outside Docker, install Python 3.12+, then:

```bash
pip install -r requirements.txt
python scrape_seo.py --input urls.txt --output data/results.csv --json data/results.json --screenshots-dir data/screenshots
```
