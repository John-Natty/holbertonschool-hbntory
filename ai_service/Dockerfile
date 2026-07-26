FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system ai-service \
    && useradd \
        --system \
        --gid ai-service \
        --home-dir /app \
        --no-create-home \
        ai-service

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=ai-service:ai-service app ./app

USER ai-service:ai-service

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health', timeout=2).read()"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
