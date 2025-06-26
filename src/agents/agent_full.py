# tool_agent.py
import operator
import os
import traceback
from typing import Annotated, TypedDict, List, Optional # Añadido Optional
import uuid
from datetime import datetime, timedelta
import re

# Langchain core y Ollama
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.utils.function_calling import convert_to_openai_tool

# Langgraph
from langgraph.checkpoint.memory import MemorySaver # Para persistencia si es necesario
from langgraph.graph import END, StateGraph

# Para las herramientas
import requests
import json

# --- Configuración del Agente y Herramienta ---
RAG_SERVICE_URL = os.getenv('RAG_SERVICE_URL', 'http://localhost:8080')
GYM_API_URL = os.getenv('GYM_API_URL', 'http://localhost:8000')
OLLAMA_MODEL_NAME = os.getenv('OLLAMA_MODEL_NAME', "qwen3:8b")

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - AGENT - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- HERRAMIENTAS ---
@tool
def external_rag_search_tool(query: str, limit: int = 3, score_threshold: float = 0.3) -> str:
    """
    Busca en una base de conocimientos general información relacionada con la consulta del usuario.
    Utiliza esta herramienta para responder preguntas generales que requieran buscar en documentos o FAQs.
    NO la uses para consultar disponibilidad o hacer reservas de servicios específicos como el gimnasio.
    La entrada 'query' debe ser la pregunta del usuario.
    """
    logger.info(f"🛠️ Herramienta RAG Externa llamada con: query='{query}', limit={limit}, threshold={score_threshold}")
    search_endpoint = f"{RAG_SERVICE_URL}/search"
    payload = {"query": query, "limit": limit, "score_threshold": score_threshold}
    try:
        response = requests.post(search_endpoint, json=payload, timeout=45)
        response.raise_for_status()
        search_data = response.json()
        if search_data and "results" in search_data and search_data["results"]:
            context_parts = [
                f"[Resultado {i+1}] Fuente: {doc.get('filename', 'Fuente desconocida')} (Relevancia: {doc.get('score', 0.0):.2f})\nContenido: {doc.get('text', 'Contenido no disponible')}\n---"
                for i, doc in enumerate(search_data["results"])
            ]
            retrieved_info = "No se encontró información relevante en la base de conocimientos para tu consulta." if not context_parts else "Información recuperada de la base de conocimientos:\n\n" + "\n".join(context_parts)
            logger.info(f"✅ Servicio RAG devolvió {search_data.get('total_results', 0)} resultados.")
        else:
            retrieved_info = "El servicio RAG no devolvió resultados válidos o la respuesta estaba vacía."
            logger.warning(f"⚠️ Servicio RAG: sin resultados o formato inesperado para query '{query}'. Respuesta: {search_data}")
    except requests.exceptions.HTTPError as http_err:
        error_details_str = http_err.response.text
        try: error_details_str = json.dumps(http_err.response.json())
        except ValueError: pass
        logger.error(f"❌ Error HTTP {http_err.response.status_code} llamando a RAG: {error_details_str}")
        retrieved_info = f"Error al contactar RAG (HTTP {http_err.response.status_code})"
    except requests.exceptions.RequestException as req_err:
        logger.error(f"❌ Error de red llamando a RAG: {req_err}")
        retrieved_info = f"Error al conectar con RAG (Red): {str(req_err)}"
    except Exception as e:
        logger.error(f"❌ Error inesperado en RAG: {e}\n{traceback.format_exc()}")
        retrieved_info = f"Error inesperado en RAG: {str(e)}"
    logger.info(f"📤 Herramienta RAG devolviendo (primeros 200 chars): {retrieved_info[:200]}...")
    return retrieved_info

@tool
def check_gym_availability(target_date: str) -> str:
    """
    Comprueba la disponibilidad de plazas en el gimnasio para una fecha y hora dadas.
    Usa esta herramienta como PRIMER PASO para cualquier consulta del usuario sobre el gimnasio o antes de intentar reservar.
    Parámetro:
    - target_date: Una cadena en formato ISO 8601 (YYYY-MM-DDTHH:MM:SS) representando la fecha y hora para comprobar la disponibilidad.
                   Si el usuario solo da una fecha, puedes asumir T08:00:00 para ver los primeros horarios disponibles de ese día.
    Devuelve una lista de horarios disponibles o un mensaje si no hay disponibilidad. Esta herramienta es de solo lectura y no hace reservas.
    """
    logger.info(f"🛠️ Herramienta Check Gym Availability llamada con: target_date='{target_date}'")
    url = f"{GYM_API_URL}/availability"
    payload = {"service_name": "gimnasio", "start_time": target_date}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            slots_data = response.json()
            if isinstance(slots_data, list) and slots_data:
                start_times = [slot.get("start_time") for slot in slots_data if slot.get("start_time")][:5]
                if start_times:
                    # Devolver el slot original pedido si está en la lista, para facilitar la confirmación
                    if target_date in start_times:
                         return f"El horario {target_date} está disponible. Otros horarios cercanos disponibles: {json.dumps(start_times)}"
                    return f"Horarios disponibles encontrados para el gimnasio cerca de {target_date}: {json.dumps(start_times)}"
                else: # Slots_data no contenía start_time válidos
                    return f"No se encontraron horarios específicos con 'start_time' en la respuesta para {target_date}. Respuesta API: {json.dumps(slots_data)[:200]}"
            elif isinstance(slots_data, list) and not slots_data: # Lista vacía
                return f"No hay horarios disponibles en el gimnasio para la fecha y hora especificadas ({target_date})."
            else: # Respuesta no es una lista o es inesperada
                 return f"Respuesta inesperada del API de disponibilidad (no es una lista de slots o está malformada): {json.dumps(slots_data)[:200]}"
        else: # Error HTTP
            logger.warning(f"Check Gym Availability: API devolvió {response.status_code}. Respuesta: {response.text[:200]}")
            return f"No se pudo verificar la disponibilidad para el gimnasio en {target_date} (código: {response.status_code}). Respuesta API: {response.text[:200]}"
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red en Check Gym Availability: {e}")
        return f"Error de red al verificar disponibilidad del gimnasio: {str(e)}"
    except Exception as e: # Otros errores (ej. JSONDecodeError si la respuesta no es JSON)
        logger.error(f"❌ Error inesperado en Check Gym Availability: {e}\n{traceback.format_exc()}")
        return f"Error inesperado al verificar disponibilidad del gimnasio: {str(e)}"

@tool
def book_gym_slot(booking_date: str, user_name: str) -> str:
    """
    Reserva un horario específico en el gimnasio para un usuario DESPUÉS de que la disponibilidad haya sido confirmada.
    ADVERTENCIA: Esta acción crea una reserva y tiene efectos secundarios.
    SOLO usa esta herramienta después de confirmar la fecha y hora EXACTAS (juntas como booking_date en formato YYYY-MM-DDTHH:MM:SS) y el nombre del huésped.
    Parámetros:
    - booking_date: Una cadena en formato ISO 8601 (YYYY-MM-DDTHH:MM:SS) representando la fecha y hora exactas a reservar.
    - user_name: El nombre completo de la persona que hace la reserva. Esto DEBE ser proporcionado por el usuario antes de llamar a esta herramienta.
    """
    logger.info(f"🛠️ Herramienta Book Gym Slot llamada para {user_name} en {booking_date}.")
    avail_url = f"{GYM_API_URL}/availability"
    avail_payload = {"service_name": "gimnasio", "start_time": booking_date}
    headers = {"Content-Type": "application/json"}
    slot_id_to_book = None
    try:
        logger.debug(f"Verificando disponibilidad exacta para {booking_date} antes de reservar...")
        avail_response = requests.post(avail_url, json=avail_payload, headers=headers, timeout=15)
        if avail_response.status_code == 200:
            slots = avail_response.json()
            if not isinstance(slots, list): # Asegurarse de que la respuesta es una lista
                logger.error(f"Respuesta de disponibilidad para {booking_date} no fue una lista: {slots}")
                return f"No se pudo confirmar la disponibilidad del horario {booking_date} (formato de respuesta incorrecto)."

            for slot in slots:
                if slot.get("start_time") == booking_date:
                    slot_id_to_book = slot.get("slot_id")
                    logger.info(f"Slot ID {slot_id_to_book} encontrado para {booking_date}.")
                    break
            if not slot_id_to_book:
                logger.warning(f"El slot deseado {booking_date} no apareció en la lista de disponibilidad exacta.")
                # Devolver los primeros slots disponibles como sugerencia puede ser útil
                sugerencias = [s.get("start_time") for s in slots if s.get("start_time")][:3]
                sugerencias_str = f" Horarios alternativos cercanos podrían ser: {', '.join(sugerencias)}." if sugerencias else ""
                return (f"El horario deseado {booking_date} no está disponible o no se pudo confirmar.{sugerencias_str} "
                        f"Por favor, primero verifica la disponibilidad general con 'check_gym_availability'.")
        else:
            logger.error(f"No se pudo verificar la disponibilidad antes de reservar (código: {avail_response.status_code}). Respuesta: {avail_response.text[:200]}")
            return f"No se pudo confirmar la disponibilidad del horario {booking_date} antes de intentar la reserva (Error API: {avail_response.status_code})."

        logger.info(f"Intentando reservar slot ID {slot_id_to_book} para {user_name}...")
        book_url = f"{GYM_API_URL}/booking"
        booking_payload = {"slot_id": slot_id_to_book, "guest_name": user_name}
        book_response = requests.post(book_url, json=booking_payload, headers=headers, timeout=15)
        if book_response.status_code == 201:
            booking_data = book_response.json()
            logger.info(f"Reserva exitosa: {booking_data}")
            return (f"Reserva exitosa para {booking_data.get('guest_name')} en el gimnasio. "
                    f"ID de la reserva: {booking_data.get('booking_id', 'No proporcionado')}, Slot ID: {booking_data.get('slot_id')}, Hora: {booking_date}.")
        elif book_response.status_code == 409:
            logger.warning(f"Conflicto de reserva para slot ID {slot_id_to_book}: {book_response.text[:200]}")
            return f"Conflicto de reserva: El horario {booking_date} (slot ID: {slot_id_to_book}) ya está reservado o lleno."
        else:
            logger.error(f"Fallo la reserva (código {book_response.status_code}): {book_response.text[:200]}")
            return f"Fallo la reserva del gimnasio (código {book_response.status_code}): {book_response.text[:200]}"
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red en Book Gym Slot: {e}")
        return f"Error de red al intentar reservar el gimnasio: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Error inesperado en Book Gym Slot: {e}\n{traceback.format_exc()}")
        return f"Error inesperado al intentar reservar el gimnasio: {str(e)}"

ALL_TOOLS_LIST = [external_rag_search_tool, check_gym_availability, book_gym_slot]

# --- 2. Definición del Estado del Agente ---
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    # Memoria para el flujo de reserva del gimnasio
    gym_slot_iso_to_book: Optional[str]         # YYYY-MM-DDTHH:MM:SS slot ofrecido/confirmado
    user_name_for_gym_booking: Optional[str]
    pending_gym_slot_confirmation: bool       # True si hemos ofrecido un slot y esperamos confirmación/nombre
    # Podríamos añadir un flag para saber si el último ToolMessage fue de check_gym_availability con éxito
    # last_tool_successful_gym_check: bool

# --- 3. Prompt del Sistema para el Agente ---
RAG_SYSTEM_PROMPT = f"""Eres un asistente de IA conversacional y útil. Ayudas con preguntas generales y gestionas reservas para el gimnasio.
Tienes acceso a las siguientes herramientas:

1.  **{ALL_TOOLS_LIST[0].name}**:
    - Descripción: {ALL_TOOLS_LIST[0].description}
    - Argumentos: {json.dumps(ALL_TOOLS_LIST[0].args, indent=2)}
    - Úsala para preguntas generales sobre el hotel, políticas, etc. NO para disponibilidad o reservas de gimnasio.

2.  **{ALL_TOOLS_LIST[1].name}**:
    - Descripción: {ALL_TOOLS_LIST[1].description}
    - Argumentos: {json.dumps(ALL_TOOLS_LIST[1].args, indent=2)}
    - DEBES usar esta herramienta PRIMERO si el usuario pregunta por la disponibilidad del gimnasio o quiere hacer una reserva.

3.  **{ALL_TOOLS_LIST[2].name}**:
    - Descripción: {ALL_TOOLS_LIST[2].description}
    - Argumentos: {json.dumps(ALL_TOOLS_LIST[2].args, indent=2)}
    - ADVERTENCIA: Esta herramienta crea una reserva REAL. ÚSALA SOLAMENTE DESPUÉS de:
        a. Haber usado '{ALL_TOOLS_LIST[1].name}' y el usuario haya indicado un horario específico de los disponibles.
        b. El usuario haya confirmado explícitamente el horario EXACTO (YYYY-MM-DDTHH:MM:SS) que desea reservar.
        c. Haber obtenido y confirmado el NOMBRE COMPLETO del usuario para la reserva. REVISA el historial de mensajes para ver si ya tienes el nombre.
    - Si el usuario quiere reservar pero no ha proporcionado toda la información (horario exacto confirmado por él Y su nombre completo), PÍDESELA ANTES de llamar a esta herramienta. No inventes el nombre del usuario.

**Contexto Adicional del Agente (Información que puedes usar para tomar decisiones):**
{{agent_scratchpad}}

**Flujo de Trabajo Detallado para Reservas de Gimnasio:**
1.  Si el usuario pregunta por el gimnasio (disponibilidad, horarios, reservar), usa SIEMPRE PRIMERO '{ALL_TOOLS_LIST[1].name}'.
    Ejemplo de argumento: {{ "target_date": "YYYY-MM-DDTHH:MM:SS" }} o {{ "target_date": "YYYY-MM-DDT08:00:00" }}.
2.  Presenta los resultados de disponibilidad al usuario de forma clara. Indica explícitamente si un slot específico que pidió está disponible o no.
3.  Si se encontraron slots y el usuario quiere reservar uno:
    a.  CONFIRMA el slot exacto (YYYY-MM-DDTHH:MM:SS) que el usuario quiere. RECUERDA ESTE SLOT.
    b.  Si ya sabes el nombre completo del usuario por mensajes anteriores, úsalo.
    c.  Si NO sabes el nombre completo, PÍDELO CLARAMENTE: "¿Cuál es tu nombre completo para la reserva?". RECUERDA EL NOMBRE CUANDO LO DEN.
    d.  Una vez que tengas el SLOT EXACTO CONFIRMADO y el NOMBRE COMPLETO DEL USUARIO, y el usuario haya dicho "sí" o "confirmo" a la reserva de ESE slot, entonces y SOLO entonces, usa '{ALL_TOOLS_LIST[2].name}'.
        Argumentos: {{ "booking_date": "SLOT_RECORDADO_YYYY-MM-DDTHH:MM:SS", "user_name": "NOMBRE_RECORDADO_COMPLETO" }}.
4.  Informa al usuario del resultado de la reserva (éxito o fallo).
5.  Si el usuario dice "sí" después de que le ofreciste un slot y le pediste el nombre, asume que el "sí" es para confirmar el slot, y procede a usar el nombre que dio (o pídelo si no lo dio junto con el "sí").

**Formato de Salida para Herramientas (Recordatorio para Qwen):**
Si decides usar una herramienta, el sistema espera que generes un objeto JSON con las claves "tool" y "tool_input".
Ejemplo: {json.dumps({"tool": "nombre_de_la_herramienta", "tool_input": {"argumento1": "valor1"}})}
SOLO genera el JSON de la herramienta, sin texto adicional antes o después, cuando llames a una herramienta.

Si puedes responder sin herramientas, simplemente proporciona la respuesta como texto.
Después de que una herramienta devuelva información (que te será proporcionada), USA ESA INFORMACIÓN para responder al usuario en lenguaje natural. NO vuelvas a llamar a la misma herramienta inmediatamente con la misma query.
"""

# --- 4. Clase del Agente RAG ---
class RagAgent:
    def __init__(self, tools: list, ollama_model_name: str = OLLAMA_MODEL_NAME):
        self._tools_map = {t.name: t for t in tools}
        if not tools: raise ValueError("RagAgent requiere al menos una herramienta.")

        try:
            tools_as_json_schema = [convert_to_openai_tool(tool) for tool in tools]
            self._llm = ChatOllama(
                model=ollama_model_name,
                temperature=0.05, # Un poco de temperatura para mejor conversación post-tool
                # format="json", # Eliminado para Qwen, confiando en el workaround y schema
            ).bind(tools=tools_as_json_schema)
            logger.info(f"🤖 LLM del Agente ({ollama_model_name}) inicializado. Herramientas vinculadas: {[t.name for t in tools]}.")
        except Exception as e:
            logger.error(f"❌ ERROR inicializando LLM ({ollama_model_name}): {e}\n{traceback.format_exc()}")
            raise

        # Definición del Grafo
        workflow = StateGraph(AgentState)
        workflow.add_node('call_llm', self.call_llm_node)
        workflow.add_node('invoke_tools_node', self.invoke_tools_node)
        # Nuevo nodo para actualizar el estado después de la respuesta del LLM (antes de decidir la herramienta)
        workflow.add_node('update_state_after_llm', self.update_state_after_llm)
        # Nuevo nodo para actualizar el estado después de la ejecución de la herramienta
        workflow.add_node('update_state_after_tool', self.update_state_after_tool)


        workflow.set_entry_point('call_llm')
        
        # Flujo: LLM -> update_state_after_llm -> Router -> (Tool o END)
        workflow.add_edge('call_llm', 'update_state_after_llm')
        workflow.add_conditional_edges(
            'update_state_after_llm', # El router ahora decide después de que el estado se haya actualizado con la última respuesta del LLM
            self.should_invoke_tool_router,
            {'invoke_tool': 'invoke_tools_node', 'respond_directly': END}
        )
        # Flujo: Tool -> update_state_after_tool -> LLM
        workflow.add_edge('invoke_tools_node', 'update_state_after_tool')
        workflow.add_edge('update_state_after_tool', 'call_llm')

        self.graph = workflow.compile(checkpointer=MemorySaver())
        logger.info("✅ Grafo del agente compilado con manejo de estado.")

    def _get_current_agent_scratchpad(self, state: AgentState) -> str:
        """Prepara una cadena de scratchpad para el LLM con el estado actual de la reserva."""
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
        """
        Intenta extraer información relevante de la última respuesta del USUARIO o del LLM
        para actualizar el estado de la reserva.
        Este nodo se ejecuta DESPUÉS de call_llm_node y ANTES de should_invoke_tool_router.
        """
        logger.debug(f"  [UpdateStateAfterLLM] Estado actual: gym_slot='{state.get('gym_slot_iso_to_book')}', user_name='{state.get('user_name_for_gym_booking')}', pending_confirm='{state.get('pending_gym_slot_confirmation')}'")
        
        # Analizar el último mensaje del usuario si el LLM está pidiendo información
        # o si el LLM acaba de presentar opciones de disponibilidad.
        # Esta lógica puede volverse compleja y depende de cómo el LLM frasea sus preguntas
        # y cómo el usuario responde.

        # Si el LLM acaba de usar `check_gym_availability` y presentó un slot específico:
        # Buscamos en el historial reciente.
        # Este es un ejemplo simplificado. Una solución más robusta usaría extracción de entidades.
        messages = state['messages']
        user_provides_name = False
        user_confirms_slot = False
        
        if len(messages) >= 2:
            last_ai_msg = messages[-2] if isinstance(messages[-1], HumanMessage) else messages[-1] # Puede ser el mismo si el último es AI
            last_human_msg_content = messages[-1].content if isinstance(messages[-1], HumanMessage) else ""

            # Heurística: Si la IA acaba de preguntar por el nombre y el usuario responde
            if isinstance(last_ai_msg, AIMessage) and \
               ("nombre completo" in last_ai_msg.content.lower() or "su nombre" in last_ai_msg.content.lower()) and \
               state.get('pending_gym_slot_confirmation'):
                # Asumimos que la respuesta del usuario es el nombre
                # Esto es una simplificación, una mejor manera sería usar extracción de entidades
                # o que el LLM confirme "Entendido, tu nombre es X. ¿Correcto?"
                if last_human_msg_content:
                    logger.info(f"    [UpdateStateAfterLLM] Usuario podría haber proporcionado nombre: '{last_human_msg_content}'")
                    state['user_name_for_gym_booking'] = last_human_msg_content.strip()
                    user_provides_name = True


            # Heurística: Si la IA ofreció un slot y el usuario dice "sí" o confirma
            if isinstance(last_ai_msg, AIMessage) and \
               state.get('pending_gym_slot_confirmation') and \
               ("desea reservar este horario" in last_ai_msg.content.lower() or "quieres este horario" in last_ai_msg.content.lower()):
                if "sí" in last_human_msg_content.lower() or "si" in last_human_msg_content.lower() or \
                   "confirmo" in last_human_msg_content.lower() or "vale" in last_human_msg_content.lower():
                    logger.info(f"    [UpdateStateAfterLLM] Usuario parece confirmar el slot pendiente.")
                    user_confirms_slot = True
                    # Si también dieron el nombre en el mismo mensaje de confirmación
                    # (ej. "Sí, soy Carlos Portilla"), el código anterior ya lo habría capturado.


        # Si tenemos un slot y un nombre y el usuario acaba de confirmar (o el LLM lo va a hacer),
        # podríamos quitar pending_gym_slot_confirmation para que el LLM proceda a book_gym_slot.
        # Pero dejaremos que el LLM tome esa decisión final basado en el scratchpad actualizado.
        
        logger.info(f"  [UpdateStateAfterLLM] Estado después de actualizar: gym_slot='{state.get('gym_slot_iso_to_book')}', user_name='{state.get('user_name_for_gym_booking')}', pending_confirm='{state.get('pending_gym_slot_confirmation')}'")
        return state

    def update_state_after_tool(self, state: AgentState) -> AgentState:
        """Actualiza el estado basado en el resultado de la herramienta."""
        last_message = state['messages'][-1]
        if isinstance(last_message, ToolMessage):
            logger.debug(f"  [UpdateStateAfterTool] Procesando ToolMessage de '{last_message.name}'")
            if last_message.name == check_gym_availability.name:
                # Parsear el resultado de check_gym_availability para ver si se ofreció un slot específico
                # y si estaba disponible.
                tool_content = last_message.content
                # Ejemplo de heurística: si la herramienta devolvió un slot específico como disponible
                # Podríamos necesitar una forma más robusta de saber qué slot se ofreció al usuario.
                # Por ahora, si la herramienta devuelve algo que no sea "No hay horarios disponibles",
                # asumimos que se le ofrecerán opciones al usuario.
                if "Horarios disponibles encontrados" in tool_content or "está disponible" in tool_content:
                    # Extraer el slot que se usó en la query de la herramienta, si es posible
                    # Esto es un poco frágil. Idealmente el LLM confirmaría el slot.
                    # Buscamos el AIMessage que llamó a la herramienta.
                    ai_call_msg = None
                    if len(state['messages']) >= 2:
                        if isinstance(state['messages'][-2], AIMessage) and state['messages'][-2].tool_calls:
                            ai_call_msg = state['messages'][-2]
                    
                    if ai_call_msg:
                        tool_call_args = ai_call_msg.tool_calls[0].get('args', {})
                        queried_date = tool_call_args.get('target_date')
                        if queried_date:
                             # Comprobar si el slot consultado está realmente en la respuesta de la herramienta.
                             # Esto es complejo porque la herramienta devuelve una lista.
                             # Por ahora, simplemente marcamos que estamos esperando confirmación.
                             # El LLM debe presentar los slots y el usuario elegir.
                            logger.info(f"    [UpdateStateAfterTool] check_gym_availability tuvo éxito. Poniendo pending_gym_slot_confirmation=True. Slot consultado: {queried_date}")
                            state['pending_gym_slot_confirmation'] = True
                            state['gym_slot_iso_to_book'] = queried_date # Tentativamente, el LLM debe confirmar cuál de los devueltos
                    else:
                        logger.warning("    [UpdateStateAfterTool] No se pudo encontrar el AIMessage que llamó a check_gym_availability para extraer target_date.")
                        state['pending_gym_slot_confirmation'] = True # Aún así, el LLM presentará opciones

                elif "No hay horarios disponibles" in tool_content:
                    logger.info("    [UpdateStateAfterTool] check_gym_availability no encontró slots. Limpiando estado de reserva.")
                    state['gym_slot_iso_to_book'] = None
                    state['pending_gym_slot_confirmation'] = False
                    # user_name_for_gym_booking se mantiene por si el usuario quiere probar otra fecha.

            elif last_message.name == book_gym_slot.name:
                logger.info("    [UpdateStateAfterTool] book_gym_slot fue llamado. Limpiando estado de reserva.")
                # Limpiar el estado después de un intento de reserva (exitoso o no)
                state['gym_slot_iso_to_book'] = None
                state['user_name_for_gym_booking'] = None # Podríamos mantenerlo si queremos, pero mejor limpiar
                state['pending_gym_slot_confirmation'] = False
        
        logger.info(f"  [UpdateStateAfterTool] Estado después de actualizar: gym_slot='{state.get('gym_slot_iso_to_book')}', user_name='{state.get('user_name_for_gym_booking')}', pending_confirm='{state.get('pending_gym_slot_confirmation')}'")
        return state


    def should_invoke_tool_router(self, state: AgentState) -> str:
        # ... (igual que antes, pero ahora después de update_state_after_llm) ...
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
                logger.warning(f"    [Router] LLM solicitó herramienta desconocida vía .tool_calls: '{tool_name}'. Ignorando.")
                last_message.tool_calls = []
                return 'respond_directly'
        
        if isinstance(last_message.content, str) and last_message.content.strip().startswith("{"):
            try:
                content_json = json.loads(last_message.content)
                logger.debug(f"    [Router] Contenido de AIMessage parseado como JSON: {content_json}")
                if isinstance(content_json, dict) and "tool" in content_json and "tool_input" in content_json:
                    tool_name = content_json["tool"]
                    tool_args = content_json["tool_input"]
                    if tool_name in self._tools_map and isinstance(tool_args, dict):
                        logger.warning(f"    [Router WORKAROUND] Detectada llamada a herramienta '{tool_name}' en .content.")
                        last_message.tool_calls = [{"name": tool_name, "args": tool_args, "id": f"qwen_tc_{uuid.uuid4().hex}"}]
                        last_message.content = "" 
                        logger.info(f"    [Router WORKAROUND] .tool_calls reconstruido: {last_message.tool_calls}")
                        return 'invoke_tool'
                    else:
                        logger.warning(f"    [Router WORKAROUND] JSON en .content parece tool_call pero nombre ('{tool_name}') desconocido o args no dict.")
                elif isinstance(content_json, dict) and "answer" in content_json:
                    logger.info("    [Router] LLM devolvió JSON con 'answer', tratando como respuesta directa.")
                    last_message.content = content_json["answer"]
                    last_message.tool_calls = []
                    return 'respond_directly'
            except json.JSONDecodeError:
                logger.debug(f"    [Router] Contenido no era JSON de tool_call esperado: '{last_message.content[:100]}...'")
            except Exception as e:
                logger.error(f"    [Router WORKAROUND] Error inesperado procesando content_json: {e}\n{traceback.format_exc()}")

        logger.info(f"    [Router] LLM no solicitó herramienta. tool_calls: {getattr(last_message, 'tool_calls', 'N/A')}, content: '{str(last_message.content)[:100]}...'")
        return 'respond_directly'

    def call_llm_node(self, state: AgentState) -> dict:
        messages = state['messages']
        
        # Crear el system prompt, inyectando el scratchpad
        agent_scratchpad_content = self._get_current_agent_scratchpad(state)
        # logger.debug(f"    [LLM Node] Contenido del Scratchpad: {agent_scratchpad_content}")
        
        # Reemplazar el placeholder en el RAG_SYSTEM_PROMPT
        # O añadirlo como un mensaje separado. Añadirlo como mensaje es más limpio.
        current_messages_for_llm = []
        system_prompt_with_scratchpad = RAG_SYSTEM_PROMPT.replace("{{agent_scratchpad}}", agent_scratchpad_content)

        # Asegurar que el SystemMessage sea el primero y único
        # y que el scratchpad esté actualizado
        has_system_message = False
        for m in messages:
            if isinstance(m, SystemMessage):
                # Reemplazar el system message existente con el actualizado (con scratchpad)
                current_messages_for_llm.append(SystemMessage(content=system_prompt_with_scratchpad))
                has_system_message = True
            else:
                current_messages_for_llm.append(m)
        
        if not has_system_message:
            current_messages_for_llm.insert(0, SystemMessage(content=system_prompt_with_scratchpad))
            logger.info("    [LLM Node] Se antepuso RAG_SYSTEM_PROMPT con scratchpad.")
        else:
            logger.info("    [LLM Node] SystemMessage actualizado con scratchpad.")

        model_name_for_log = getattr(self._llm, 'model', getattr(getattr(self._llm, 'llm', None), 'model', 'modelo_desconocido'))
        logger.info(f"  [LLM Node] Llamando al LLM ({model_name_for_log}) con {len(current_messages_for_llm)} mensajes.")
        if current_messages_for_llm: logger.debug(f"    Último mensaje al LLM: {type(current_messages_for_llm[-1]).__name__} {str(current_messages_for_llm[-1].content)[:100]}...")
        
        try:
            ai_message_response = self._llm.invoke(current_messages_for_llm)
        except Exception as e:
            logger.error(f"❌ ERROR durante la invocación del LLM: {e}\n{traceback.format_exc()}")
            ai_message_response = AIMessage(content=f"Error al procesar con LLM: {e}", tool_calls=[])
        
        if not hasattr(ai_message_response, 'tool_calls') or not isinstance(ai_message_response.tool_calls, list):
            ai_message_response.tool_calls = [] 
        
        logger.info(f"    Respuesta CRUDA del LLM (AIMessage): tool_calls={ai_message_response.tool_calls}, content='{str(ai_message_response.content)[:200]}...'")
        
        # Devolver solo el nuevo AIMessage para ser añadido al estado.
        # Los nodos de actualización de estado se encargarán de modificar el estado existente.
        return {'messages': [ai_message_response]}


    def invoke_tools_node(self, state: AgentState) -> AgentState: # Ahora devuelve el estado completo
        logger.info("  [Tools Node] Intentando invocar herramientas.")
        last_ai_message = state['messages'][-1] 

        if not (isinstance(last_ai_message, AIMessage) and hasattr(last_ai_message, 'tool_calls') and \
                isinstance(last_ai_message.tool_calls, list) and len(last_ai_message.tool_calls) > 0):
            error_msg = "Error: AIMessage inválida o sin tool_calls para invocación en invoke_tools_node."
            logger.error(f"    [Tools Node] {error_msg} tool_calls: {getattr(last_ai_message, 'tool_calls', 'NoAttr')}")
            # Devolver el estado actual con un ToolMessage de error añadido.
            # El grafo espera que los nodos devuelvan el estado completo o un dict para actualizarlo.
            return {**state, "messages": state["messages"] + [ToolMessage(content=error_msg, tool_call_id="error_no_valid_tool_calls")]}


        tool_messages = []
        for tool_call in last_ai_message.tool_calls:
            # ... (lógica de invocación de herramienta igual que antes) ...
            if not isinstance(tool_call, dict):
                logger.error(f"    [Tools Node] Elemento tool_call no es un dict: {tool_call}")
                tool_messages.append(ToolMessage(content=f"Error: tool_call malformado: {tool_call}", tool_call_id=f"err_tc_{uuid.uuid4().hex}"))
                continue

            tool_name = tool_call.get('name')
            tool_args = tool_call.get('args')
            tool_call_id = tool_call.get('id', f"tc_{uuid.uuid4().hex}") 

            if not tool_name or not isinstance(tool_args, dict):
                error_msg = f"Error: llamada a herramienta malformada. Nombre: '{tool_name}', Args: {type(tool_args)}"
                logger.error(f"    [Tools Node] {error_msg}")
                tool_messages.append(ToolMessage(content=error_msg, tool_call_id=tool_call_id, name=tool_name or "unknown_tool"))
                continue
            
            logger.info(f"    [Tools Node] Invocando herramienta: '{tool_name}' con args: {tool_args}")
            if tool_name not in self._tools_map:
                result_content = f"Error: Herramienta desconocida o no disponible: '{tool_name}'."
                logger.error(f"    [Tools Node] {result_content}")
            else:
                try: 
                    valid_args = True; missing_args = []
                    if tool_name == book_gym_slot.name:
                        if 'booking_date' not in tool_args: missing_args.append('booking_date')
                        if 'user_name' not in tool_args: missing_args.append('user_name')
                    elif tool_name == check_gym_availability.name and 'target_date' not in tool_args:
                        missing_args.append('target_date')
                    elif tool_name == external_rag_search_tool.name and 'query' not in tool_args:
                        missing_args.append('query')
                    
                    if missing_args:
                        result_content = f"Error: Para '{tool_name}' faltan los argumentos requeridos: {', '.join(missing_args)}. Argumentos recibidos: {tool_args}"
                        logger.warning(f"    [Tools Node] {result_content}"); valid_args = False
                    if valid_args: result_content = self._tools_map[tool_name].invoke(tool_args)
                except Exception as e:
                    logger.error(f"      [Tools Node] ERROR ejecutando herramienta {tool_name}: {e}\n{traceback.format_exc()}")
                    result_content = f"Error al ejecutar la herramienta {tool_name}: {str(e)}"
            
            tool_messages.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content))
            logger.info(f"    [Tools Node] Herramienta '{tool_name}' invocada. Resultado añadido.")
        
        logger.info(f"    [Tools Node] Todos las tool_calls procesadas. {len(tool_messages)} ToolMessages generados.")
        # Devolver el estado actual con los nuevos ToolMessages añadidos.
        return {**state, "messages": state["messages"] + tool_messages}


# --- Bloque Principal ---
if __name__ == '__main__':
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