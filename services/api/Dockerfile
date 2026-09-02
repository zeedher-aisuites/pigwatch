FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/python/pigwatch-schemas packages/python/pigwatch-schemas
COPY services/api services/api

RUN python -m pip install --no-cache-dir ./packages/python/pigwatch-schemas \
    && python -m pip install --no-cache-dir ./services/api

EXPOSE 8000

CMD ["uvicorn", "pigwatch_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
