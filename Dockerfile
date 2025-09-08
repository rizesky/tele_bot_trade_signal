FROM python:3.12-slim

# Set environment variables
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Jakarta \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies in one layer
RUN apt-get update && apt-get install -y \
    tzdata \
    ca-certificates \
    chromium \
    chromium-driver \
    build-essential \
    gcc \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/*

# Configure Playwright to use system Chromium
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/bin
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip cache purge \
    && apt-get purge -y build-essential gcc \
    && apt-get autoremove -y

# Copy application files
COPY *.py ./
COPY templates/ ./templates/

# Create directories and setup user
RUN mkdir -p logs charts \
    && groupadd -r appuser \
    && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('trading_bot.db').close()" || exit 1

CMD ["python", "main.py"]