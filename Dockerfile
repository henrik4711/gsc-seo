FROM python:3.12-slim-bookworm

# Install Playwright system dependencies manually (avoid --with-deps font issues)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libxshmfence1 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxkbcommon0 \
    libcups2 \
    libdbus-1-3 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrender1 \
    libxtst6 \
    libglib2.0-0 \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install ONLY Chromium browser (no --with-deps to avoid font package errors)
RUN playwright install chromium

COPY . .
RUN chmod +x start.sh

EXPOSE 8501

CMD ["./start.sh"]
