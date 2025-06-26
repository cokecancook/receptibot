import operator
from typing import Annotated, TypedDict, Optional
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage, ToolMessage
import logging

logger = logging.getLogger(__name__)

# --- Definición del Estado del Agente ---
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    # Memoria para el flujo de reserva del gimnasio
    gym_slot_iso_to_book: Optional[str]         # YYYY-MM-DDTHH:MM:SS slot ofrecido/confirmado
    user_name_for_gym_booking: Optional[str]
    pending_gym_slot_confirmation: bool       # True si hemos ofrecido un slot y esperamos confirmación/nombre

def get_current_agent_scratchpad(state: AgentState) -> str:
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

def update_state_after_llm(state: AgentState) -> AgentState:
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

def update_state_after_tool(state: AgentState, check_gym_availability, book_gym_slot) -> AgentState:
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