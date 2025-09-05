FROM python:3.12-bookworm

WORKDIR /app

COPY requirements.txt .

# Install Playwright and headless Chromium only
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt  && \
    playwright install --with-deps chromium-headless-shell

COPY . .

CMD ["python", "main.py"]
