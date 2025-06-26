import os
import uuid
import re
import json
import traceback
import logging
from typing import List

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
import uvicorn
import requests # Para el health check del RAG service

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from state import AgentState
# RAG_SERVICE_URL ahora se refiere al servicio Flask en tu app.py
from tools import ALL_TOOLS_LIST, check_gym_availability, book_gym_slot, RAG_SERVICE_URL
from system_prompt import RAG_SYSTEM_PROMPT

# --- Configuración del Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - AGENT_API - %(levelname)s - %(message)s' # Identificador para logs
)
logger = logging.getLogger(__name__)

# --- Configuración del Modelo y API ---
OLLAMA_MODEL_NAME = os.getenv('OLLAMA_MODEL_NAME', "qwen3:8b") # o "qwen3:8b" si es el que usas

# --- Modelos Pydantic para la API ---
class UserInput(BaseModel):
    message: str
    # Los elementos del estado de la conversación se manejarán internamente o se pasarán si es necesario
    # por ahora, el thread_id gestionará la persistencia del estado completo.

class AgentResponse(BaseModel):
    reply: str
    thread_id: str
    # Podríamos añadir más campos si es necesario, como tool_calls si queremos exponerlas.

# --- Clase del Agente RAG (Adaptada) ---
class RagAgent:
    def __init__(self, tools: list, ollama_model_name: str = OLLAMA_MODEL_NAME):
        self._tools_map = {t.name: t for t in tools}
        if not tools: raise ValueError("RagAgent requiere al menos una herramienta.")

        try:
            tools_as_json_schema = [convert_to_openai_tool(tool) for tool in tools]
            self._llm = ChatOllama(
                model=ollama_model_name,
                temperature=0.05,
            ).bind(tools=tools_as_json_schema)
            logger.info(f"🤖 LLM del Agente ({ollama_model_name}) inicializado. Herramientas vinculadas: {[t.name for t in tools]}.")
        except Exception as e:
            logger.error(f"❌ ERROR inicializando LLM ({ollama_model_name}): {e}\n{traceback.format_exc()}")
            raise

        workflow = StateGraph(AgentState)
        workflow.add_node('call_llm', self.call_llm_node)
        workflow.add_node('invoke_tools_node', self.invoke_tools_node)
        workflow.add_node('update_state_after_llm', self.update_state_after_llm)
        workflow.add_node('update_state_after_tool', self.update_state_after_tool)

        workflow.set_entry_point('call_llm')
        workflow.add_edge('call_llm', 'update_state_after_llm')
        workflow.add_conditional_edges(
            'update_state_after_llm',
            self.should_invoke_tool_router,
            {'invoke_tool': 'invoke_tools_node', 'respond_directly': END}
        )
        workflow.add_edge('invoke_tools_node', 'update_state_after_tool')
        workflow.add_edge('update_state_after_tool', 'call_llm')

        self.graph = workflow.compile(checkpointer=MemorySaver())
        logger.info("✅ Grafo del agente compilado con manejo de estado.")

    def _get_current_agent_scratchpad(self, state: AgentState) -> str:
        lines = []
        if state.get('gym_slot_iso_to_book'):
            lines.append(f"- Slot de gimnasio preseleccionado para reserva: {state['gym_slot_iso_to_book']}")
        if state.get('user_name_for_gym_booking'):
            lines.append(f"- Nombre de usuario para la reserva: {state['user_name_for_gym_booking']}")
        if state.get('pending_gym_slot_confirmation'):
            lines.append("- Actualmente estamos esperando la confirmación del usuario para un slot de gimnasio y/o su nombre.")
        
        if not lines:
            return "No hay información de contexto adicional para la reserva de gimnasio en este momento."
        return "Contexto actual de la reserva de gimnasio:\n" + "\n".join(lines)

    def update_state_after_llm(self, state: AgentState) -> AgentState:
        logger.debug(f"  [UpdateStateAfterLLM] Estado actual: gym_slot='{state.get('gym_slot_iso_to_book')}', user_name='{state.get('user_name_for_gym_booking')}', pending_confirm='{state.get('pending_gym_slot_confirmation')}'")
        messages = state['messages']
        
        if len(messages) >= 2:
            last_ai_msg = messages[-2] if isinstance(messages[-1], HumanMessage) else messages[-1]
            last_human_msg_content = messages[-1].content if isinstance(messages[-1], HumanMessage) else ""

            if isinstance(last_ai_msg, AIMessage) and \
               ("nombre completo" in last_ai_msg.content.lower() or "su nombre" in last_ai_msg.content.lower()) and \
               state.get('pending_gym_slot_confirmation'):
                if last_human_msg_content:
                    logger.info(f"    [UpdateStateAfterLLM] Usuario podría haber proporcionado nombre: '{last_human_msg_content}'")
                    state['user_name_for_gym_booking'] = last_human_msg_content.strip()

            if isinstance(last_ai_msg, AIMessage) and \
               state.get('pending_gym_slot_confirmation') and \
               ("desea reservar este horario" in last_ai_msg.content.lower() or "quieres este horario" in last_ai_msg.content.lower()):
                if "sí" in last_human_msg_content.lower() or "si" in last_human_msg_content.lower() or \
                   "confirmo" in last_human_msg_content.lower() or "vale" in last_human_msg_content.lower():
                    logger.info(f"    [UpdateStateAfterLLM] Usuario parece confirmar el slot pendiente.")
        
        logger.info(f"  [UpdateStateAfterLLM] Estado después de actualizar: gym_slot='{state.get('gym_slot_iso_to_book')}', user_name='{state.get('user_name_for_gym_booking')}', pending_confirm='{state.get('pending_gym_slot_confirmation')}'")
        return state

    def update_state_after_tool(self, state: AgentState) -> AgentState:
        last_message = state['messages'][-1]
        if isinstance(last_message, ToolMessage):
            logger.debug(f"  [UpdateStateAfterTool] Procesando ToolMessage de '{last_message.name}'")
            if last_message.name == check_gym_availability.name:
                tool_content = last_message.content
                if "Horarios disponibles encontrados" in tool_content or "está disponible" in tool_content:
                    ai_call_msg = None
                    if len(state['messages']) >= 2:
                        if isinstance(state['messages'][-2], AIMessage) and state['messages'][-2].tool_calls:
                            ai_call_msg = state['messages'][-2]
                    
                    if ai_call_msg:
                        tool_call_args = ai_call_msg.tool_calls[0].get('args', {})
                        queried_date = tool_call_args.get('target_date')
                        if queried_date:
                            logger.info(f"    [UpdateStateAfterTool] check_gym_availability tuvo éxito. Poniendo pending_gym_slot_confirmation=True. Slot consultado: {queried_date}")
                            state['pending_gym_slot_confirmation'] = True
                            state['gym_slot_iso_to_book'] = queried_date
                    else:
                        logger.warning("    [UpdateStateAfterTool] No se pudo encontrar AIMessage que llamó a check_gym_availability.")
                        state['pending_gym_slot_confirmation'] = True

                elif "No hay horarios disponibles" in tool_content:
                    logger.info("    [UpdateStateAfterTool] check_gym_availability no encontró slots. Limpiando estado.")
                    state['gym_slot_iso_to_book'] = None
                    state['pending_gym_slot_confirmation'] = False

            elif last_message.name == book_gym_slot.name:
                logger.info("    [UpdateStateAfterTool] book_gym_slot fue llamado. Limpiando estado de reserva.")
                state['gym_slot_iso_to_book'] = None
                state['user_name_for_gym_booking'] = None
                state['pending_gym_slot_confirmation'] = False
        
        logger.info(f"  [UpdateStateAfterTool] Estado después de actualizar: gym_slot='{state.get('gym_slot_iso_to_book')}', user_name='{state.get('user_name_for_gym_booking')}', pending_confirm='{state.get('pending_gym_slot_confirmation')}'")
        return state

    def should_invoke_tool_router(self, state: AgentState) -> str:
        logger.debug("  [Router: Decidiendo siguiente paso...]")
        last_message = state['messages'][-1] if state['messages'] else None
        if not isinstance(last_message, AIMessage):
            logger.warning("    [Router] Último mensaje no es AIMessage.")
            return 'respond_directly'

        if hasattr(last_message, 'tool_calls') and isinstance(last_message.tool_calls, list) and last_message.tool_calls:
            tool_name = last_message.tool_calls[0].get('name', 'N/A')
            if tool_name in self._tools_map:
                logger.info(f"    [Router] LLM solicitó herramienta vía .tool_calls: '{tool_name}'.")
                return 'invoke_tool'
            else:
                logger.warning(f"    [Router] LLM solicitó herramienta desconocida: '{tool_name}'. Ignorando.")
                last_message.tool_calls = []
                return 'respond_directly'
        
        if isinstance(last_message.content, str) and last_message.content.strip().startswith("{"):
            try:
                content_json = json.loads(last_message.content)
                if isinstance(content_json, dict) and "tool" in content_json and "tool_input" in content_json:
                    tool_name = content_json["tool"]
                    tool_args = content_json["tool_input"]
                    if tool_name in self._tools_map and isinstance(tool_args, dict):
                        logger.warning(f"    [Router WORKAROUND] Detectada llamada a herramienta '{tool_name}' en .content.")
                        last_message.tool_calls = [{"name": tool_name, "args": tool_args, "id": f"qwen_tc_{uuid.uuid4().hex}"}]
                        last_message.content = "" 
                        return 'invoke_tool'
                elif isinstance(content_json, dict) and "answer" in content_json:
                    logger.info("    [Router] LLM devolvió JSON con 'answer', tratando como respuesta directa.")
                    last_message.content = content_json["answer"]
                    last_message.tool_calls = []
                    return 'respond_directly'
            except json.JSONDecodeError: pass # No era JSON de tool_call
            except Exception as e: logger.error(f"    [Router WORKAROUND] Error procesando content_json: {e}")

        logger.info(f"    [Router] LLM no solicitó herramienta. tool_calls: {getattr(last_message, 'tool_calls', 'N/A')}")
        return 'respond_directly'

    def call_llm_node(self, state: AgentState) -> dict:
        messages = state['messages']
        agent_scratchpad_content = self._get_current_agent_scratchpad(state)
        system_prompt_with_scratchpad = RAG_SYSTEM_PROMPT.replace("{{agent_scratchpad}}", agent_scratchpad_content)
        
        current_messages_for_llm = []
        has_system_message = False
        for m in messages:
            if isinstance(m, SystemMessage):
                current_messages_for_llm.append(SystemMessage(content=system_prompt_with_scratchpad))
                has_system_message = True
            else:
                current_messages_for_llm.append(m)
        
        if not has_system_message:
            current_messages_for_llm.insert(0, SystemMessage(content=system_prompt_with_scratchpad))
            logger.info("    [LLM Node] Se antepuso RAG_SYSTEM_PROMPT con scratchpad.")
        else:
            logger.info("    [LLM Node] SystemMessage actualizado con scratchpad.")

        model_name_for_log = getattr(self._llm, 'model', 'modelo_desconocido')
        logger.info(f"  [LLM Node] Llamando al LLM ({model_name_for_log}) con {len(current_messages_for_llm)} mensajes.")
        
        try:
            ai_message_response = self._llm.invoke(current_messages_for_llm)
        except Exception as e:
            logger.error(f"❌ ERROR durante la invocación del LLM: {e}\n{traceback.format_exc()}")
            ai_message_response = AIMessage(content=f"Error al procesar con LLM: {e}", tool_calls=[])
        
        if not hasattr(ai_message_response, 'tool_calls') or not isinstance(ai_message_response.tool_calls, list):
            ai_message_response.tool_calls = [] 
        
        logger.info(f"    Respuesta del LLM (AIMessage): tool_calls={ai_message_response.tool_calls}, content='{str(ai_message_response.content)[:200]}...'")
        return {'messages': [ai_message_response]}

    def invoke_tools_node(self, state: AgentState) -> AgentState:
        logger.info("  [Tools Node] Intentando invocar herramientas.")
        last_ai_message = state['messages'][-1] 

        if not (isinstance(last_ai_message, AIMessage) and hasattr(last_ai_message, 'tool_calls') and \
                isinstance(last_ai_message.tool_calls, list) and len(last_ai_message.tool_calls) > 0):
            error_msg = "Error: AIMessage inválida o sin tool_calls para invocación."
            logger.error(f"    [Tools Node] {error_msg} tc: {getattr(last_ai_message, 'tool_calls', 'NoAttr')}")
            return {**state, "messages": state["messages"] + [ToolMessage(content=error_msg, tool_call_id="error_no_tc")]}

        tool_messages = []
        for tool_call in last_ai_message.tool_calls:
            if not isinstance(tool_call, dict):
                logger.error(f"    [Tools Node] Elemento tool_call no es un dict: {tool_call}")
                tool_messages.append(ToolMessage(content=f"Error: tc malformado: {tool_call}", tool_call_id=f"err_tc_{uuid.uuid4().hex}"))
                continue

            tool_name = tool_call.get('name')
            tool_args = tool_call.get('args')
            tool_call_id = tool_call.get('id', f"tc_{uuid.uuid4().hex}") 

            if not tool_name or not isinstance(tool_args, dict):
                error_msg = f"Error: llamada a herramienta malformada. Nombre: '{tool_name}', Args: {type(tool_args)}"
                logger.error(f"    [Tools Node] {error_msg}")
                tool_messages.append(ToolMessage(content=error_msg, tool_call_id=tool_call_id, name=tool_name or "unknown"))
                continue
            
            logger.info(f"    [Tools Node] Invocando: '{tool_name}' args: {tool_args}")
            if tool_name not in self._tools_map:
                result_content = f"Error: Herramienta desconocida: '{tool_name}'."
            else:
                try: 
                    missing_args = []
                    # Validación de args (simplificada del original)
                    if tool_name == book_gym_slot.name:
                        if 'booking_date' not in tool_args: missing_args.append('booking_date')
                        if 'user_name' not in tool_args: missing_args.append('user_name')
                    elif tool_name == check_gym_availability.name and 'target_date' not in tool_args:
                        missing_args.append('target_date')
                    # external_rag_search_tool tiene 'query' como obligatorio por defecto en su signatura
                    
                    if missing_args:
                        result_content = f"Error: Para '{tool_name}' faltan args: {', '.join(missing_args)}. Recibido: {tool_args}"
                    else: result_content = self._tools_map[tool_name].invoke(tool_args)
                except Exception as e:
                    logger.error(f"      [Tools Node] ERROR ejecutando {tool_name}: {e}\n{traceback.format_exc()}")
                    result_content = f"Error al ejecutar {tool_name}: {str(e)}"
            
            tool_messages.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content))
            logger.info(f"    [Tools Node] Herramienta '{tool_name}' invocada.")
        
        return {**state, "messages": state["messages"] + tool_messages}

# --- Inicialización de FastAPI y Agente ---
app = FastAPI(title="Agente Conversacional (FastAPI)", version="1.0") # Nombre cambiado para claridad
rag_agent_instance = None # Se inicializará en startup

@app.on_event("startup")
async def startup_event():
    global rag_agent_instance
    logger.info("🚀 Iniciando la API del Agente (FastAPI)...")
    try:
        # El health check apunta al servicio RAG Flask en RAG_SERVICE_URL (tu app.py)
        rag_health = requests.get(f"{RAG_SERVICE_URL}/health", timeout=10)
        rag_health.raise_for_status()
        health_data = rag_health.json()
        logger.info(f"💚 Estado del servicio RAG (Flask en {RAG_SERVICE_URL}): {health_data.get('status', 'desconocido')}")
        if health_data.get('status') not in ['healthy', 'degraded']:
            logger.warning(f"⚠️ El servicio RAG (Flask) reportó un estado no saludable: {health_data}. Funcionalidad de búsqueda limitada.")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ No se pudo conectar al servicio RAG (Flask en {RAG_SERVICE_URL}): {e}. Asegúrate de que tu app.py (Flask) esté ejecutándose.")

    try:
        rag_agent_instance = RagAgent(tools=ALL_TOOLS_LIST)
        logger.info("✅ Agente RAG (del agent_api) inicializado exitosamente con todas las herramientas.")
    except Exception as e:
        logger.critical(f"❌ Error crítico inicializando RagAgent: {e}\n{traceback.format_exc()}")
        raise RuntimeError(f"No se pudo inicializar RagAgent: {e}") from e

# --- Endpoints de la API ---
@app.post("/chat/{thread_id}", response_model=AgentResponse)
async def chat_with_agent(thread_id: str, user_input: UserInput):
    if rag_agent_instance is None:
        raise HTTPException(status_code=503, detail="El agente no está inicializado. Revisa los logs.")

    logger.info(f"📬 Usuario (Thread: {thread_id}): '{user_input.message}'")
    config = {"configurable": {"thread_id": thread_id}}

    current_graph_state = rag_agent_instance.graph.get_state(config)
    initial_custom_state_if_needed = {}
    if not current_graph_state or not current_graph_state.values.get("messages"):
        initial_custom_state_if_needed = {
            "gym_slot_iso_to_book": None,
            "user_name_for_gym_booking": None,
            "pending_gym_slot_confirmation": False,
        }
        logger.info(f"Thread '{thread_id}' parece nuevo. Inicializando estado custom para el agente.")
    
    input_for_graph = {
        "messages": [HumanMessage(content=user_input.message)],
        **initial_custom_state_if_needed
    }

    final_ai_response_content = "El agente no generó respuesta."
    try:
        for _ in rag_agent_instance.graph.stream(input_for_graph, config=config, stream_mode="values"):
            pass 
    
    except Exception as stream_err:
        logger.error(f"❌ Error en stream para thread {thread_id}: {stream_err}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error procesando solicitud: {stream_err}")

    final_graph_state_after_stream = rag_agent_instance.graph.get_state(config)
    if final_graph_state_after_stream and final_graph_state_after_stream.values['messages']:
        final_agent_message = final_graph_state_after_stream.values['messages'][-1]
        
        if isinstance(final_agent_message, AIMessage) and isinstance(final_agent_message.content, str):
            cleaned_content = re.sub(r"<think>.*?</think>\s*\n?", "", final_agent_message.content, flags=re.DOTALL).strip()
        else:
            cleaned_content = getattr(final_agent_message, 'content', "No content in final message.")

        if isinstance(final_agent_message, AIMessage) and \
           (not hasattr(final_agent_message, 'tool_calls') or not final_agent_message.tool_calls):
            final_ai_response_content = cleaned_content
        elif isinstance(final_agent_message, AIMessage) and final_agent_message.tool_calls:
            final_ai_response_content = f"(Agente usó herramienta: {final_agent_message.tool_calls[0]['name']}. Esperando que el flujo continúe o la respuesta sea procesada.)"
            if cleaned_content and cleaned_content != final_ai_response_content : 
                 final_ai_response_content += f"\nRazonamiento (si lo hay): {cleaned_content}"
        elif isinstance(final_agent_message, ToolMessage):
             final_ai_response_content = f"(Agente procesó herramienta: {final_agent_message.name}. El flujo continuará para generar una respuesta en lenguaje natural.)"
        elif final_ai_response_content == "El agente no generó respuesta.":
             final_ai_response_content = "El agente terminó de procesar pero no generó un mensaje final de texto explícito en este paso."
    else: 
        final_ai_response_content = "No se pudo obtener el estado final del agente o no hay mensajes."
        logger.error(f"No se pudo obtener estado final para thread {thread_id} o no había mensajes.")

    logger.info(f"💬 Agente (Thread: {thread_id}): '{final_ai_response_content}'")
    return AgentResponse(reply=final_ai_response_content, thread_id=thread_id)

@app.get("/agent-health") # Endpoint de salud específico para el agente
async def agent_health_check():
    # Podrías añadir comprobaciones de dependencias aquí (Ollama, etc.)
    return {"status": "healthy", "agent_ollama_model": OLLAMA_MODEL_NAME}

if __name__ == '__main__':
    logger.info(f"Iniciando servidor Uvicorn para la API del AGENTE en el modelo {OLLAMA_MODEL_NAME}...")
    # Asegúrate de que las variables de entorno como RAG_SERVICE_URL, GYM_API_URL y OLLAMA_MODEL_NAME
    # estén configuradas en tu entorno antes de ejecutar esto.
    # El servicio RAG (Flask, tu app.py) debe estar ejecutándose por separado.
    # Esta API del agente se ejecutará en el puerto 8001.
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")