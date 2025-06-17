from flask import Flask, request, jsonify
from qdrant_client import QdrantClient
import requests
import logging
import os

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración desde variables de entorno
QDRANT_HOST = os.getenv('QDRANT_HOST', 'localhost')
QDRANT_PORT = int(os.getenv('QDRANT_PORT', '6333'))
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'localhost')
OLLAMA_PORT = int(os.getenv('OLLAMA_PORT', '11434'))
COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'documents')
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'nomic-embed-text')

# Inicializar clientes
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
ollama_url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

logger.info(f"🔗 Conectando a Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
logger.info(f"🔗 Conectando a Ollama: {OLLAMA_HOST}:{OLLAMA_PORT}")
logger.info(f"🧠 Modelo de embeddings: {EMBEDDING_MODEL}")
logger.info(f"📦 Colección: {COLLECTION_NAME}")

def get_embedding(text: str):
    """Obtener embedding usando Ollama"""
    try:
        response = requests.post(
            f"{ollama_url}/api/embeddings",
            json={
                "model": EMBEDDING_MODEL,
                "prompt": text
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except Exception as e:
        logger.error(f"❌ Error obteniendo embedding: {e}")
        raise

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de salud"""
    try:
        # Verificar conexión a Qdrant
        collections = qdrant_client.get_collections()
        qdrant_status = "ok"
        
        # Verificar conexión a Ollama
        ollama_response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        ollama_status = "ok" if ollama_response.status_code == 200 else "error"
        
        return jsonify({
            "status": "healthy",
            "qdrant": qdrant_status,
            "ollama": ollama_status,
            "collection": COLLECTION_NAME,
            "embedding_model": EMBEDDING_MODEL
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

@app.route('/search', methods=['POST'])
def search():
    """Endpoint principal de búsqueda"""
    try:
        # Obtener la pregunta del request
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                "error": "Campo 'query' requerido",
                "example": {"query": "servicios del hotel"}
            }), 400
        
        query = data['query'].strip()
        
        if not query:
            return jsonify({
                "error": "La consulta no puede estar vacía"
            }), 400
        
        # Parámetros opcionales
        limit = int(data.get('limit', 5))
        score_threshold = float(data.get('score_threshold', 0.5))
        
        logger.info(f"🔍 Búsqueda: '{query}' (limit={limit}, threshold={score_threshold})")
        
        # Obtener embedding de la consulta
        query_embedding = get_embedding(query)
        
        # Buscar en Qdrant
        search_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            limit=limit,
            score_threshold=score_threshold
        )
        
        # Si no encuentra nada, buscar sin threshold
        if not search_results:
            logger.warning("⚠️ Sin resultados con threshold, buscando sin filtro...")
            search_results = qdrant_client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=0.0
            )
        
        # Procesar resultados
        documents = []
        for result in search_results:
            doc = {
                "text": result.payload.get("text", ""),
                "filename": result.payload.get("filename", ""),
                "score": round(result.score, 4),
                "chunk_index": result.payload.get("chunk_index", 0),
                "file_type": result.payload.get("file_type", "")
            }
            documents.append(doc)
        
        response = {
            "query": query,
            "results": documents,
            "total_results": len(documents),
            "parameters": {
                "limit": limit,
                "score_threshold": score_threshold
            }
        }
        
        logger.info(f"✅ Encontrados {len(documents)} documentos")
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ Error en búsqueda: {e}")
        return jsonify({
            "error": "Error interno del servidor",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)