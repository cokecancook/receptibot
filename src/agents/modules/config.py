import os
import redis

# --- Configuración del Agente y Herramienta ---
RAG_SERVICE_URL = os.getenv('RAG_SERVICE_URL', 'http://localhost:8080')
GYM_API_URL = os.getenv('GYM_API_URL', 'http://localhost:8000')
OLLAMA_MODEL_NAME = os.getenv('OLLAMA_MODEL_NAME', "caporti/qwen3-capor")

# --- Configuración Redis para Persistencia ---
REDIS_HOST = os.getenv('REDIS_HOST', 'redis_stack_container')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'redis_password')  # ✅ CAMBIO: password por defecto
REDIS_PREFIX = os.getenv('REDIS_PREFIX', 'agent_session')  # Prefijo para las keys

# Configuración de TTL (Time To Live) para sesiones
SESSION_TTL_HOURS = int(os.getenv('SESSION_TTL_HOURS', '24'))  # 24 horas por defecto
SESSION_TTL_SECONDS = SESSION_TTL_HOURS * 3600

# URL de conexión Redis completa (útil para algunas librerías)
def get_redis_url():
    """Construye la URL de conexión Redis"""
    auth_part = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
    return f"redis://{auth_part}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Configuración del pool de conexiones
REDIS_CONNECTION_POOL_CONFIG = {
    'host': REDIS_HOST,
    'port': REDIS_PORT,
    'db': REDIS_DB,
    'password': REDIS_PASSWORD,
    'decode_responses': True,  # Importante para manejar strings correctamente
    'max_connections': 20,     # Pool de conexiones
    'retry_on_timeout': True,
    'socket_timeout': 5,       # Timeout de socket en segundos
    'socket_connect_timeout': 5,
}