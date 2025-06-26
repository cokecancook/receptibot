import os

# --- Configuración del Agente y Herramienta ---
RAG_SERVICE_URL = os.getenv('RAG_SERVICE_URL', 'http://localhost:8080')
GYM_API_URL = os.getenv('GYM_API_URL', 'http://localhost:8000')
OLLAMA_MODEL_NAME = os.getenv('OLLAMA_MODEL_NAME', "qwen3:8b")