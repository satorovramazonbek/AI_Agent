FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY jarvis ./jarvis
COPY config ./config
RUN pip install .

# Root bo'lmagan foydalanuvchi
RUN useradd --create-home --uid 1000 jarvis && mkdir -p /tmp/jarvis && chown jarvis /tmp/jarvis
USER jarvis

ENV JARVIS_HOST=0.0.0.0 \
    JARVIS_PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["python", "-m", "jarvis.main"]
