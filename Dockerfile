FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Single worker required — APScheduler runs in-process
# Render sets PORT env var; default to 8000 for local dev
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
