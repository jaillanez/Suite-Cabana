# API de producción. Contexto: backend/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Dependencias primero: cambian menos que el código y quedan en caché.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && rm -rf app

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --no-deps . \
    && useradd --system --uid 10001 --home /app suite \
    && mkdir -p /data/media && chown suite /data/media

USER suite
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-server-header"]
