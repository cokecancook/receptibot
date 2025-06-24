import operator
from typing import Annotated, TypedDict, List, Optional
from langchain_core.messages import AnyMessage

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    # Memoria para el flujo de reserva del gimnasio
    gym_slot_iso_to_book: Optional[str]         # YYYY-MM-DDTHH:MM:SS slot ofrecido/confirmado
    user_name_for_gym_booking: Optional[str]
    pending_gym_slot_confirmation: bool       # True si hemos ofrecido un slot y esperamos confirmación/nombre
    # Podríamos añadir un flag para saber si el último ToolMessage fue de check_gym_availability con éxito
    # last_tool_successful_gym_check: bool