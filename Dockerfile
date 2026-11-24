FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=wsgi:app

WORKDIR /app

RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /var/lib/unique/uploads \
 && chown -R app:app /var/lib/unique /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R app:app /app /var/lib/unique

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["sh", "-c", "python scripts/wait_for_db.py && exec gunicorn --bind ${APP_HOST:-0.0.0.0}:${APP_PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --access-logfile - --error-logfile - wsgi:app"]
