FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY api/api-services/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY generator/ ./generator/

COPY api/api-services/ .

EXPOSE 8000

CMD ["python", "app.py"]