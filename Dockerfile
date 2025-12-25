# Используем актуальную версию образа, которую просит Playwright в логах
FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY main.py .

EXPOSE 8000

CMD ["python", "main.py"]