# app.py
from flask import Flask, request, jsonify
from qdrant_client import QdrantClient
import requests
import logging
import os
import traceback # Para un logging de errores más detallado

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración desde variables de entorno
QDRANT_HOST = os.getenv('QDRANT_HOST', 'localhost')
QDRANT_PORT = int(os.getenv('QDRANT_PORT', '6333'))
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'localhost')
OLLAMA_PORT = int(os.getenv('OLLAMA_PORT', '11434'))
COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'documents') # Asegúrate de que esta colección exista en Qdrant
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'nomic-embed-text') # Asegúrate de que este modelo esté en Ollama

# Inicializar clientes
try:
    qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10) # Añadido timeout
    logger.info(f"✅ Conectado exitosamente a Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
except Exception as e:
    logger.error(f"❌ FALLO AL CONECTAR CON QDRANT: {QDRANT_HOST}:{QDRANT_PORT} - {e}")
    qdrant_client = None # Marcar como no disponible

ollama_url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

logger.info(f"🔗 Intentando conectar a Ollama: {OLLAMA_HOST}:{OLLAMA_PORT}")
logger.info(f"🧠 Modelo de embeddings (Ollama): {EMBEDDING_MODEL}")
logger.info(f"📦 Colección Qdrant: {COLLECTION_NAME}")

def get_embedding(text: str, attempt=1, max_attempts=3):
    """Obtener embedding usando Ollama con reintentos."""
    try:
        logger.info(f"🔄 Obteniendo embedding para texto (intento {attempt}/{max_attempts}): '{text[:50]}...'")
        response = requests.post(
            f"{ollama_url}/api/embeddings",
            json={
                "model": EMBEDDING_MODEL,
                "prompt": text,
                # "keep_alive": "5m" # Opcional: puede ayudar a mantener el modelo cargado en Ollama
            },
            timeout=30  # Timeout para la petición de embedding
        )
        response.raise_for_status()
        embedding = response.json().get("embedding")
        if not embedding:
            logger.error(f"❌ Embedding vacío recibido de Ollama para el modelo {EMBEDDING_MODEL}.")
            raise ValueError("Embedding vacío recibido de Ollama")
        logger.info(f"👍 Embedding obtenido exitosamente (longitud: {len(embedding)})")
        return embedding
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red obteniendo embedding (intento {attempt}/{max_attempts}): {e}")
        if attempt < max_attempts:
            logger.info(f"Retrying embedding generation for: '{text[:50]}...'")
            return get_embedding(text, attempt + 1, max_attempts)
        raise
    except Exception as e:
        logger.error(f"❌ Error inesperado obteniendo embedding (intento {attempt}): {e}")
        logger.error(traceback.format_exc())
        if attempt < max_attempts and not isinstance(e, ValueError): # No reintentar si el embedding está vacío
            logger.info(f"Retrying embedding generation for: '{text[:50]}...'")
            return get_embedding(text, attempt + 1, max_attempts)
        raise

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de salud"""
    service_status = {"status": "healthy"}
    http_status_code = 200

    # Verificar conexión a Qdrant
    if qdrant_client:
        try:
            qdrant_client.get_collections() # Una operación ligera para verificar la conexión
            service_status["qdrant_connection"] = "ok"
        except Exception as e:
            logger.warning(f"⚠️ Problema de conexión con Qdrant en health check: {e}")
            service_status["qdrant_connection"] = "error"
            service_status["qdrant_error"] = str(e)
            service_status["status"] = "degraded"
            # http_status_code = 503 # Service Unavailable
    else:
        service_status["qdrant_connection"] = "unavailable (failed to initialize)"
        service_status["status"] = "degraded"
        # http_status_code = 503

    # Verificar conexión a Ollama (y si el modelo de embedding existe)
    try:
        ollama_models_response = requests.get(f"{ollama_url}/api/tags", timeout=10)
        ollama_models_response.raise_for_status()
        models_data = ollama_models_response.json()
        available_models = [m.get("name") for m in models_data.get("models", [])]
        if any(EMBEDDING_MODEL in m_name for m_name in available_models):
            service_status["ollama_connection"] = "ok"
            service_status["ollama_embedding_model_found"] = True
        else:
            service_status["ollama_connection"] = "ok"
            service_status["ollama_embedding_model_found"] = False
            service_status["ollama_embedding_model_warning"] = f"Modelo '{EMBEDDING_MODEL}' no encontrado en Ollama. Modelos disponibles: {available_models}"
            service_status["status"] = "degraded"
            # http_status_code = 503

    except requests.exceptions.RequestException as e:
        logger.warning(f"⚠️ Problema de conexión con Ollama en health check: {e}")
        service_status["ollama_connection"] = "error"
        service_status["ollama_error"] = str(e)
        service_status["status"] = "degraded"
        # http_status_code = 503
    except Exception as e:
        logger.warning(f"⚠️ Error inesperado en health check de Ollama: {e}")
        service_status["ollama_connection"] = "error_unexpected"
        service_status["ollama_error"] = str(e)
        service_status["status"] = "degraded"


    service_status["qdrant_target_collection"] = COLLECTION_NAME
    service_status["embedding_model_configured"] = EMBEDDING_MODEL
    
    # Si algún componente crítico falla, el estado general debería ser unhealthy
    if service_status.get("qdrant_connection") != "ok" or \
       service_status.get("ollama_connection") != "ok" or \
       not service_status.get("ollama_embedding_model_found", False):
        http_status_code = 503 # Service Unavailable

    return jsonify(service_status), http_status_code

@app.route('/search', methods=['POST'])
def search():
    """Endpoint principal de búsqueda"""
    if not qdrant_client:
        logger.error("❌ Qdrant client no está disponible. No se puede realizar la búsqueda.")
        return jsonify({
            "error": "Servicio de base de datos no disponible",
            "details": "El cliente Qdrant no pudo inicializarse."
        }), 503

    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({"error": "Campo 'query' requerido", "example": {"query": "servicios del hotel"}}), 400
        
        query = data['query'].strip()
        if not query:
            return jsonify({"error": "La consulta no puede estar vacía"}), 400
        
        limit = int(data.get('limit', 5))
        score_threshold = float(data.get('score_threshold', 0.3)) # Umbral un poco más bajo por defecto
        
        logger.info(f"🔍 Búsqueda recibida: '{query}' (limit={limit}, threshold={score_threshold})")
        
        query_embedding = get_embedding(query)
        
        logger.info(f"🔎 Buscando en Qdrant (colección: {COLLECTION_NAME}) con {len(query_embedding)} dimensiones de vector.")
        search_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            limit=limit,
            score_threshold=score_threshold,
            # with_payload=True # Asegúrate de que esto esté implícito o explícito si es necesario
        )
        
        if not search_results and score_threshold > 0.0: # Solo reintenta si había un threshold
            logger.warning(f"⚠️ Sin resultados con threshold={score_threshold}. Reintentando sin filtro de score (limit={limit})...")
            search_results = qdrant_client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding,
                limit=limit,
                # score_threshold=0.0 # Opcional: o simplemente no lo pases si tu cliente Qdrant lo maneja
            )
        
        documents = []
        for result in search_results:
            doc_payload = result.payload if result.payload else {}
            doc = {
                "id": result.id, # Incluir el ID del punto puede ser útil
                "text": doc_payload.get("text", doc_payload.get("page_content", "")), # Comprobar 'page_content' como fallback
                "filename": doc_payload.get("filename", doc_payload.get("source", "")), # Comprobar 'source'
                "score": round(result.score, 4),
                "chunk_index": doc_payload.get("chunk_index", 0),
                "file_type": doc_payload.get("file_type", "")
                # Añade cualquier otro campo del payload que quieras devolver
            }
            documents.append(doc)
        
        response_data = {
            "query": query,
            "results": documents,
            "total_results": len(documents),
            "parameters": {
                "limit_used": limit, # Lo que se usó en la última búsqueda
                "score_threshold_requested": data.get('score_threshold', 0.3), # Lo que se pidió
                "score_threshold_applied_initially": score_threshold # Lo que se aplicó primero
            }
        }
        
        logger.info(f"✅ Búsqueda completada. Encontrados {len(documents)} documentos para la consulta '{query}'.")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"❌ Error catastrófico en la búsqueda: {e}")
        logger.error(traceback.format_exc()) # Log completo del traceback
        return jsonify({
            "error": "Error interno del servidor durante la búsqueda.",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    # Es mejor no usar debug=True en producción real.
    # Para producción, considera un servidor WSGI como Gunicorn o uWSGI.
    app.run(host='0.0.0.0', port=8080, debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true')