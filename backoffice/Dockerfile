FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system backoffice \
    && useradd \
        --system \
        --gid backoffice \
        --home-dir /app \
        --no-create-home \
        backoffice

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=backoffice:backoffice app ./app
COPY --chown=backoffice:backoffice migrations ./migrations

USER backoffice:backoffice

EXPOSE 5000

CMD ["python", "-m", "flask", "--app", "app:create_app", "run", "--host=0.0.0.0", "--port=5000"]
