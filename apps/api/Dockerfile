# Build context is apps/api (App Platform: source_dir: apps/api).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so a code-only change reuses this layer. psycopg2-binary
# ships manylinux wheels, so no compiler is needed in the image.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# main.py mounts app/playground through StaticFiles with a RELATIVE path, so
# the process has to start from /app or that mount raises at import time.
EXPOSE 8080

# App Platform injects PORT. The default matches docker-compose's mapping.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
