FROM python:3.11-slim

# Системные пакеты
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# pip + uv для быстрой установки зависимостей
RUN pip install --no-cache-dir uv

WORKDIR /app

# Сначала зависимости (для кэша Docker)
COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

# Потом код
COPY . .

# Создаём непривилегированного юзера
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
