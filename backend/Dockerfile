# Backend image: FastAPI served by uvicorn. The SQLite database lives in /data, which docker-compose mounts as a volume
# so it survives rebuilds. One process only: the built-in scheduler (reminder e-mails) must not run twice.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN useradd --create-home --uid 10001 hub && mkdir -p /data && chown hub /data
USER hub

ENV DATABASE_URL=sqlite:////data/hub.db
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# Bring the database up to date, then serve. A failed migration stops the container instead of serving a broken schema.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
