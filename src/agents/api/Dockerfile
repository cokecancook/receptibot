# Dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY src/agents/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src
ENV PYTHONPATH=/app

EXPOSE 8081

# Ejecuta directamente el script
CMD ["python", "src/agents/api/main.py"]
