FROM python:3.11-slim

WORKDIR /app

# Системные зависимости для сборки C-расширений
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

RUN pip install --upgrade pip && pip install --no-cache-dir .

COPY src/app/ ./src/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]