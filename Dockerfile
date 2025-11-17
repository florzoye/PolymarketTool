FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

# Создаем пользователя для безопасности
RUN useradd -m -r botuser && chown -R botuser:botuser /app
USER botuser


CMD ["python", "main.py"]