import traceback
import uuid
import json
import re
import os
from datetime import datetime

from langchain_core.messages import SystemMessage, AIMessage, ToolMessage, HumanMessage
from langchain_ollama import ChatOllama
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

# Importa tu checkpointer personalizado y el estado
from .config import OLLAMA_MODEL_NAME
from .state import AgentState, get_current_agent_scratchpad
from .redis_checkpointer import RedisCheckpointer
from .prompt import RAG_SYSTEM_PROMPT

import logging
logger = logging.getLogger(__name__)

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

        workflow.set_entry_point('call_llm')
        
        # Flujo simplificado: El LLM decide si usar una herramienta o terminar.
        workflow.add_conditional_edges(
            'call_llm',
            self.should_invoke_tool_router,
            {
                'invoke_tool': 'invoke_tools_node',
                '__end__': END # Usar __end__ para terminar explícitamente la ejecución
            }
        )
        # Después de usar una herramienta, siempre volvemos a llamar al LLM con el resultado.
        workflow.add_edge('invoke_tools_node', 'call_llm')

        try:
            # Usando TU implementación de RedisCheckpointer
            checkpointer = RedisCheckpointer()
            self.graph = workflow.compile(checkpointer=checkpointer)
            logger.info("✅ Grafo del agente compilado con la clase RedisCheckpointer local.")
        except Exception as e:
            logger.error(f"❌ Error inicializando RedisCheckpointer, usando MemorySaver como fallback: {e}")
            self.graph = workflow.compile(checkpointer=MemorySaver())
            logger.warning("⚠️ Usando MemorySaver como fallback - Las conversaciones no persistirán")

    def should_invoke_tool_router(self, state: AgentState) -> str:
        """
        Router mejorado que inspecciona la última respuesta de la IA.
        Busca llamadas a herramientas tanto en .tool_calls como en .content (workaround).
        """
        logger.debug("  [Router: Decidiendo siguiente paso...]")
        last_message = state['messages'][-1]
        
        if not isinstance(last_message, AIMessage):
            return '__end__'

        if isinstance(last_message.content, str):
            json_match = re.search(r'\{.*\}', last_message.content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    content_json = json.loads(json_str)
                    tool_name = content_json.get("name") or content_json.get("tool")
                    tool_args = content_json.get("arguments") or content_json.get("tool_input")

                    if tool_name in self._tools_map and isinstance(tool_args, dict):
                        logger.warning(f"    [Router WORKAROUND] Detectada llamada a herramienta '{tool_name}' en .content.")
                        last_message.tool_calls = [{"name": tool_name, "args": tool_args, "id": f"llm_tc_{uuid.uuid4().hex}"}]
                        last_message.content = "" 
                        return 'invoke_tool'
                except (json.JSONDecodeError, AttributeError):
                     pass

        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info("    [Router] LLM solicitó herramienta correctamente vía .tool_calls.")
            return 'invoke_tool'

        logger.info("    [Router] El LLM no solicitó herramienta. La ejecución termina.")
        return '__end__'

    def call_llm_node(self, state: AgentState) -> dict:
        """Llama al LLM. Devuelve solo el nuevo mensaje de la IA."""
        messages = state['messages']
        system_prompt_with_scratchpad = RAG_SYSTEM_PROMPT.replace("{{agent_scratchpad}}", get_current_agent_scratchpad(state))
        
        current_messages_for_llm = [SystemMessage(content=system_prompt_with_scratchpad)]
        current_messages_for_llm.extend([m for m in messages if not isinstance(m, SystemMessage)])
        
        logger.info(f"  [LLM Node] Llamando al LLM con {len(current_messages_for_llm)} mensajes.")
        
        try:
            ai_message_response = self._llm.invoke(current_messages_for_llm)
        except Exception as e:
            logger.error(f"❌ ERROR durante la invocación del LLM: {e}\n{traceback.format_exc()}")
            ai_message_response = AIMessage(content=f"Error al procesar con LLM: {e}", tool_calls=[])
        
        return {'messages': [ai_message_response]}

    def invoke_tools_node(self, state: AgentState) -> dict:
        """Invoca las herramientas solicitadas. Devuelve solo los nuevos mensajes de herramienta."""
        last_ai_message = state['messages'][-1]
        tool_messages = []
        
        if not (hasattr(last_ai_message, 'tool_calls') and last_ai_message.tool_calls):
            return {"messages": [ToolMessage(content="Error: Se intentó llamar a herramientas pero no se encontraron tool_calls válidas.", tool_call_id="error_no_tool_calls")]}

        for tool_call in last_ai_message.tool_calls:
            tool_name = tool_call.get('name')
            tool_args = tool_call.get('args', {})
            tool_call_id = tool_call.get('id')

            logger.info(f"    [Tools Node] Invocando herramienta: '{tool_name}' con args: {tool_args}")
            if tool_name not in self._tools_map:
                result_content = f"Error: Herramienta desconocida: '{tool_name}'."
            else:
                try:
                    result_content = self._tools_map[tool_name].invoke(tool_args)
                except Exception as e:
                    logger.error(f"      [Tools Node] ERROR ejecutando herramienta {tool_name}: {e}\n{traceback.format_exc()}")
                    result_content = f"Error al ejecutar la herramienta {tool_name}: {str(e)}"
            
            tool_messages.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=str(result_content)))

        return {"messages": tool_messages}