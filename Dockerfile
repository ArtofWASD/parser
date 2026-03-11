# Используем актуальную версию образа, которую просит Playwright в логах
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект (включая папку parsers)
COPY . .

EXPOSE 8000

# Запускаем через uvicorn напрямую для лучшей стабильности
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]