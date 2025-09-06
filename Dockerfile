FROM python:3.12-bookworm

# Add locale environment variables (important for plawyright in the docker)
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

WORKDIR /app

COPY requirements.txt .

# Install Playwright and headless Chromium only
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt  && \
    playwright install --with-deps chromium-headless-shell

COPY . .

CMD ["python", "main.py"]