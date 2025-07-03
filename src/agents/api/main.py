import os
import re
import logging
import time
import uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# --- Importaciones de tu proyecto ---
from src.agents.modules.agent import RagAgent
from src.agents.modules.tools import ALL_TOOLS_LIST
from src.agents.modules.redis_checkpointer import RedisCheckpointer
from src.agents.modules.metriclogger import MetricLogger
from src.agents.modules.config import OLLAMA_MODEL_NAME

# --- Configuración del Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Variables Globales para los componentes ---
agent_instance = None
redis_checkpointer = None
metric_logger = None

# --- Función de inicialización centralizada ---
def initialize_components():
    """
    Inicializa el RagAgent, RedisCheckpointer y MetricLogger.
    Se llama una vez cuando el servidor de la aplicación se inicia.
    """
    global agent_instance, redis_checkpointer, metric_logger
    if agent_instance is None:
        try:
            logger.info("🚀 Inicializando RagAgent...")
            agent_instance = RagAgent(tools=ALL_TOOLS_LIST)
            logger.info("✅ RagAgent inicializado correctamente.")

            logger.info("🚀 Inicializando RedisCheckpointer...")
            redis_checkpointer = RedisCheckpointer()
            logger.info("✅ RedisCheckpointer inicializado correctamente.")
            
            logger.info("🚀 Inicializando MetricLogger...")
            metric_logger = MetricLogger()
            logger.info("📊 MetricLogger inicializado correctamente.")

        except Exception as e:
            logger.critical(f"❌ Error crítico durante la inicialización de componentes: {e}", exc_info=True)
            agent_instance = None
            redis_checkpointer = None
            metric_logger = None

# ✅ SOLUCIÓN: Llama a la función de inicialización directamente al iniciar el script.
# Esto reemplaza el obsoleto @app.before_first_request.
initialize_components()

# --- Funciones de Ayuda ---
def clean_agent_response(content):
    """Limpia la respuesta final del agente para el usuario."""
    if isinstance(content, str):
        return re.sub(r"<think>.*?</think>\s*\n?", "", content, flags=re.DOTALL).strip()
    return str(content) if content else "El agente no generó una respuesta textual."

def validate_thread_id(thread_id):
    """Valida el formato del thread_id para seguridad y consistencia."""
    if not thread_id or not isinstance(thread_id, str) or len(thread_id) > 100:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', thread_id))

def log_execution_metric(metric_name: str, execution_time: float):
    """Registra una métrica de tiempo de ejecución si el logger está disponible."""
    if metric_logger:
        try:
            timestamp = datetime.now(timezone.utc)
            metric_logger.log_metric(timestamp, OLLAMA_MODEL_NAME, metric_name, execution_time)
        except Exception as e:
            logger.warning(f"⚠️ No se pudo registrar la métrica '{metric_name}': {e}")


# --- Endpoints de la API ---

@app.route('/chat', methods=['POST'])
def chat_with_agent():
    start_time = time.time()
    
    if not agent_instance or not redis_checkpointer:
        return jsonify({"error": "El Agente o el Checkpointer no están inicializados. Revise los logs del servidor."}), 503

    data = request.get_json()
    if not data or not data.get('message') or not isinstance(data.get('message'), str):
        return jsonify({"error": "El campo 'message' es requerido y debe ser un string."}), 400

    message = data['message'].strip()
    if not message:
        return jsonify({"error": "El mensaje no puede estar vacío."}), 400
    if len(message) > 2000:
        return jsonify({"error": "Mensaje demasiado largo (máximo 2000 caracteres)."}), 400

    thread_id = data.get('thread_id')
    if not thread_id:
        thread_id = f'session-{uuid.uuid4()}'
    
    if not validate_thread_id(thread_id):
        return jsonify({"error": "thread_id inválido. Solo se permiten caracteres alfanuméricos, '-' y '_'."}), 400

    logger.info(f"📬 Mensaje recibido para thread '{thread_id}': '{message[:100]}'")

    config = {"configurable": {"thread_id": thread_id}}
    input_for_graph = {"messages": [HumanMessage(content=message)]}
    tools_used = set()

    try:
        final_state = None
        for event in agent_instance.graph.stream(input_for_graph, config=config, stream_mode="values"):
            final_state = event
            if event.get('messages'):
                for msg in event['messages']:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            tools_used.add(tool_call['name'])

        if not final_state or not final_state.get('messages'):
            raise ValueError("El grafo no produjo un estado final con mensajes.")
        
        final_messages = final_state.get('messages', [])
        response_content = clean_agent_response(final_messages[-1].content)
        
        execution_time = time.time() - start_time
        log_execution_metric("ejecucion_total", execution_time)
        if not tools_used:
            log_execution_metric("ejecucion_sin_tools", execution_time)
        for tool in tools_used:
            log_execution_metric(f"ejecucion_con_{tool}", execution_time)

        logger.info(f"💬 Respuesta para '{thread_id}' en {execution_time:.2f}s: '{response_content[:100]}'")
        
        return jsonify({
            "response": response_content,
            "thread_id": thread_id,
            "execution_time_seconds": round(execution_time, 2),
            "tools_used": list(tools_used),
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        execution_time = time.time() - start_time
        log_execution_metric("ejecucion_error", execution_time)
        logger.error(f"❌ Error durante la interacción del agente para '{thread_id}': {e}", exc_info=True)
        return jsonify({"error": f"Error interno del servidor: {e}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Verifica el estado de la aplicación y sus dependencias."""
    status_code = 200
    health_info = {
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "agent": "initialized" if agent_instance else "not_initialized",
        "redis": "not_initialized",
        "metrics": "initialized" if metric_logger else "not_initialized"
    }

    if not agent_instance:
        health_info["status"] = "degraded"
        status_code = 503

    if redis_checkpointer:
        try:
            redis_checkpointer.redis_client.ping()
            health_info["redis"] = "connected"
        except Exception as e:
            health_info["redis"] = f"error: {str(e)}"
            health_info["status"] = "degraded"
            status_code = 503
            
    return jsonify(health_info), status_code


@app.route('/sessions', methods=['GET'])
def list_sessions():
    """Lista las sesiones activas almacenadas en Redis."""
    if not redis_checkpointer:
        return jsonify({"error": "El servicio de sesiones (Redis) no está disponible."}), 503
    
    limit = request.args.get('limit', default=50, type=int)
    sessions = redis_checkpointer.list_active_sessions(limit=min(limit, 200))
    return jsonify({"sessions": sessions, "count": len(sessions)})

@app.route('/sessions/<string:thread_id>', methods=['GET'])
def get_session_history(thread_id):
    """Obtiene el historial de conversación de una sesión específica."""
    if not validate_thread_id(thread_id):
        return jsonify({"error": "thread_id inválido."}), 400
    if not agent_instance:
        return jsonify({"error": "El Agente no está disponible."}), 503
        
    try:
        config = {"configurable": {"thread_id": thread_id}}
        history = agent_instance.graph.get_state(config)
        
        if not history.values['messages']:
             return jsonify({"message": "Sesión no encontrada o vacía.", "thread_id": thread_id}), 404
        
        messages = [msg.dict() for msg in history.values['messages']]
        return jsonify({"thread_id": thread_id, "history": messages})
    except Exception as e:
        logger.error(f"Error al obtener historial para '{thread_id}': {e}", exc_info=True)
        return jsonify({"error": "No se pudo recuperar el historial de la sesión."}), 500

@app.route('/sessions/<string:thread_id>', methods=['DELETE'])
def delete_session(thread_id):
    """Elimina una sesión de conversación."""
    if not validate_thread_id(thread_id):
        return jsonify({"error": "thread_id inválido."}), 400
    if not redis_checkpointer:
        return jsonify({"error": "El servicio de sesiones (Redis) no está disponible."}), 503

    try:
        cleared = redis_checkpointer.clear_session(thread_id)
        if cleared:
            logger.info(f"🗑️ Sesión '{thread_id}' eliminada correctamente.")
            return jsonify({"status": "deleted", "thread_id": thread_id})
        else:
            return jsonify({"status": "not_found", "thread_id": thread_id}), 404
    except Exception as e:
        logger.error(f"Error al eliminar la sesión '{thread_id}': {e}", exc_info=True)
        return jsonify({"error": "Ocurrió un error al eliminar la sesión."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081)