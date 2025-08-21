FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Install dependencies for chromium and fonts
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-liberation \
        wget \
        ca-certificates \
        curl \
        unzip && \
    rm -rf /var/lib/apt/lists/*

# Environment variables for Selenium to find binaries
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER=/usr/bin/chromedriver

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY scrape_seo.py /app/scrape_seo.py
COPY urls.txt /app/urls.txt

# Create data directory for outputs
RUN mkdir -p /app/data/screenshots /app/data/screenshots_meta

ENTRYPOINT ["python", "/app/scrape_seo.py"]
CMD ["--input", "/app/urls.txt", "--output", "/app/data/results.csv", "--json", "/app/data/results.json", "--screenshots-dir", "/app/data/screenshots", "--delay", "2.0"]


