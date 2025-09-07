FROM python:3.12-bookworm

# Add locale and timezone environment variables (important for playwright in the docker)
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV TZ=Asia/Jakarta

WORKDIR /app

COPY requirements.txt .

# Install timezone data and Playwright with headless Chromium
RUN apt-get update && \
    apt-get install -y tzdata && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium-headless-shell

COPY . .

CMD ["python", "main.py"]