import traceback
import re
import requests
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from .config import RAG_SERVICE_URL, OLLAMA_MODEL_NAME
from .tools import ALL_TOOLS_LIST
from .agent import RagAgent

import logging
logger = logging.getLogger(__name__)

def main():
    """Main CLI execution function."""
    logger.info("🚀 Iniciando el script del agente RAG...")
    try:
        rag_health = requests.get(f"{RAG_SERVICE_URL}/health", timeout=10)
        rag_health.raise_for_status()
        health_data = rag_health.json()
        logger.info(f"💚 Estado del servicio RAG: {health_data.get('status', 'desconocido')}")
        if health_data.get('status') not in ['healthy', 'degraded']: 
            logger.warning(f"⚠️ El servicio RAG reportó un estado no saludable: {health_data}. Saliendo.")
            exit(1)
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ No se pudo conectar al servicio RAG: {e}. Asegúrate de que app.py esté ejecutándose.")
        exit(1)

    try:
        rag_agent_instance = RagAgent(tools=ALL_TOOLS_LIST)
        logger.info("✅ Agente RAG inicializado exitosamente con todas las herramientas.")
        thread_id_counter = 0
        
        # Inicializar el estado para el primer turno de cada conversación
        current_conversation_state = {
            "messages": [],
            "gym_slot_iso_to_book": None,
            "user_name_for_gym_booking": None,
            "pending_gym_slot_confirmation": False,
        }

        while True:
            thread_id_counter += 1
            current_thread_id = f"rag-cli-{thread_id_counter}"
            config = {"configurable": {"thread_id": current_thread_id}}
            if thread_id_counter > 1: # Reiniciar estado para una "nueva" simulación de conversación
                 current_conversation_state = {
                    "messages": [], # El historial de mensajes se obtendrá del checkpointer
                    "gym_slot_iso_to_book": None,
                    "user_name_for_gym_booking": None,
                    "pending_gym_slot_confirmation": False,
                }

            print(f"\n--- Conversación (ID: {current_thread_id}) ---")
            try: user_input = input("👤 Tú: ")
            except KeyboardInterrupt: print("\n👋 Saliendo..."); break
            if user_input.lower() in ["salir", "exit", "quit"]: print("👋 ¡Adiós!"); break
            if not user_input.strip(): continue

            logger.info(f"📬 Usuario: '{user_input}' (Thread: {current_thread_id})")
            
            # El input para el stream del grafo debe ser el estado completo o las partes que actualizan el estado.
            input_for_graph = {
                "messages": [HumanMessage(content=user_input)],
                "gym_slot_iso_to_book": current_conversation_state["gym_slot_iso_to_book"],
                "user_name_for_gym_booking": current_conversation_state["user_name_for_gym_booking"],
                "pending_gym_slot_confirmation": current_conversation_state["pending_gym_slot_confirmation"],
            }
            
            final_ai_response_content = "El agente no generó respuesta."
            final_event_state = None
            try:
                for event in rag_agent_instance.graph.stream(input_for_graph, config=config, stream_mode="values"):
                    # El último evento "values" tendrá el estado final de esa ejecución del stream
                    final_event_state = event 
                
                # Actualizar nuestro estado de conversación local con el estado final del grafo
                if final_event_state:
                    current_conversation_state["gym_slot_iso_to_book"] = final_event_state.get("gym_slot_iso_to_book")
                    current_conversation_state["user_name_for_gym_booking"] = final_event_state.get("user_name_for_gym_booking")
                    current_conversation_state["pending_gym_slot_confirmation"] = final_event_state.get("pending_gym_slot_confirmation")
                    # Los mensajes se actualizan automáticamente por MemorySaver y el operador add

            except Exception as stream_err:
                logger.error(f"❌ Error en stream: {stream_err}\n{traceback.format_exc()}")
                final_ai_response_content = "Error procesando solicitud."
            
            # Obtener la respuesta final del historial de mensajes ACTUALIZADO del checkpointer
            final_graph_state_after_stream = rag_agent_instance.graph.get_state(config) # Estado persistido
            if final_graph_state_after_stream and final_graph_state_after_stream.values['messages']:
                final_agent_message = final_graph_state_after_stream.values['messages'][-1]
                
                # Limpiar <think> tags de la respuesta final si es un AIMessage
                if isinstance(final_agent_message, AIMessage) and isinstance(final_agent_message.content, str):
                    cleaned_content = re.sub(r"<think>.*?</think>\s*\n?", "", final_agent_message.content, flags=re.DOTALL).strip()
                else:
                    cleaned_content = getattr(final_agent_message, 'content', "No content in final message.")

                if isinstance(final_agent_message, AIMessage) and \
                   (not hasattr(final_agent_message, 'tool_calls') or not final_agent_message.tool_calls):
                    final_ai_response_content = cleaned_content
                elif isinstance(final_agent_message, AIMessage) and final_agent_message.tool_calls:
                    final_ai_response_content = f"(Agente usó herramienta: {final_agent_message.tool_calls[0]['name']}. Esperando siguiente paso o respuesta procesada...)"
                    if cleaned_content: # Si hay contenido además de la tool_call (como el <think>)
                        final_ai_response_content += f"\nRazonamiento: {cleaned_content}"
                elif isinstance(final_agent_message, ToolMessage):
                     final_ai_response_content = f"(Agente procesó herramienta: {final_agent_message.name}. Contenido: {str(final_agent_message.content)[:100]}...)"
                elif final_ai_response_content == "El agente no generó respuesta.":
                     final_ai_response_content = "El agente terminó de procesar pero no generó un mensaje final de texto."
            else: 
                final_ai_response_content = "No se pudo obtener el estado final del agente."

            print(f"🤖 Agente: {final_ai_response_content}")
            logger.info(f"💬 Agente: '{final_ai_response_content}'")
    except Exception as e:
        logger.critical(f"❌ Error crítico: {e}\n{traceback.format_exc()}")
        if "OLLAMA_BASE_URL" in str(e) or "Connection refused" in str(e):
             logger.error(f"   Verifica Ollama. Modelo: {OLLAMA_MODEL_NAME}")
        logger.error(f"   Verifica modelo Ollama ('{OLLAMA_MODEL_NAME}') y conexión a RAG/Gym APIs.")

if __name__ == '__main__':
    main() 