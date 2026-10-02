# SproutMe Flask API
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

ENV PYTHONUNBUFFERED=1
ENV WEB_EVENTS_FILE_CACHE=/tmp/sproutme_web_events_catalog.json

EXPOSE 8080

CMD gunicorn flask_app:app --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 8 --timeout 120 --graceful-timeout 30 --keep-alive 65 --access-logfile - --error-logfile - --capture-output
