import traceback
from langchain_core.tools import tool
import requests
import json
from datetime import datetime
from src.utils.metriclogger import MetricLogger

from .config import RAG_SERVICE_URL, GYM_API_URL, OLLAMA_MODEL_NAME

import logging
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
    MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, 'tool_called:external_rag_search_tool', 1)
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
        try:
            error_details_str = json.dumps(http_err.response.json())
        except ValueError:
            pass
        logger.error(f"❌ Error HTTP {http_err.response.status_code} llamando a RAG: {error_details_str}")
        retrieved_info = f"Error al contactar RAG (HTTP {http_err.response.status_code})"
    except requests.exceptions.RequestException as req_err:
        logger.error(f"❌ Error de red llamando a RAG: {req_err}")
        retrieved_info = f"Error al conectar con RAG (Red): {str(req_err)}"
    except Exception as e:
        logger.error(f"❌ Error inesperado en RAG: {e}\n{traceback.format_exc()}")
        retrieved_info = f"Error inesperado en RAG: {str(e)}"
    logger.info(f"📤 Herramienta RAG devolviendo (primeros 200 chars): {retrieved_info[:200]}...")
    MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:external_rag_search_tool', 1)
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
    MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, 'tool_called:check_gym_availability', 1)
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
                    if target_date in start_times:
                        MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:check_gym_availability', 1)
                        return f"El horario {target_date} está disponible. Otros horarios cercanos disponibles: {json.dumps(start_times)}"
                    MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:check_gym_availability', 1)
                    return f"Horarios disponibles encontrados para el gimnasio cerca de {target_date}: {json.dumps(start_times)}"
                else:
                    MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:check_gym_availability', 1)
                    return f"No se encontraron horarios específicos con 'start_time' en la respuesta para {target_date}. Respuesta API: {json.dumps(slots_data)[:200]}"
            elif isinstance(slots_data, list) and not slots_data:
                MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:check_gym_availability', 1)
                return f"No hay horarios disponibles en el gimnasio para la fecha y hora especificadas ({target_date})."
            else:
                MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:check_gym_availability', 1)
                return f"Respuesta inesperada del API de disponibilidad (no es una lista de slots o está malformada): {json.dumps(slots_data)[:200]}"
        else:
            logger.warning(f"Check Gym Availability: API devolvió {response.status_code}. Respuesta: {response.text[:200]}")
            MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:check_gym_availability', 1)
            return f"No se pudo verificar la disponibilidad para el gimnasio en {target_date} (código: {response.status_code}). Respuesta API: {response.text[:200]}"
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red en Check Gym Availability: {e}")
        MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:check_gym_availability', 1)
        return f"Error de red al verificar disponibilidad del gimnasio: {str(e)}"
    except Exception as e: # Otros errores (ej. JSONDecodeError si la respuesta no es JSON)
        logger.error(f"❌ Error inesperado en Check Gym Availability: {e}\n{traceback.format_exc()}")
        MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:check_gym_availability', 1)
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
    MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, 'tool_called:book_gym_slot', 1)
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
                MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:book_gym_slot', 1)
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
            MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:book_gym_slot', 1)
            return (f"Reserva exitosa para {booking_data.get('guest_name')} en el gimnasio. "
                    f"ID de la reserva: {booking_data.get('booking_id', 'No proporcionado')}, Slot ID: {booking_data.get('slot_id')}, Hora: {booking_date}.")
        elif book_response.status_code == 409:
            logger.warning(f"Conflicto de reserva para slot ID {slot_id_to_book}: {book_response.text[:200]}")
            MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:book_gym_slot', 1)
            return f"Conflicto de reserva: El horario {booking_date} (slot ID: {slot_id_to_book}) ya está reservado o lleno."
        else:
            logger.error(f"Fallo la reserva (código {book_response.status_code}): {book_response.text[:200]}")
            MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:book_gym_slot', 1)
            return f"Fallo la reserva del gimnasio (código {book_response.status_code}): {book_response.text[:200]}"
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red en Book Gym Slot: {e}")
        MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:book_gym_slot', 1)
        return f"Error de red al intentar reservar el gimnasio: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Error inesperado en Book Gym Slot: {e}\n{traceback.format_exc()}")
        MetricLogger().log_metric(datetime.now(), OLLAMA_MODEL_NAME, f'tool_return:book_gym_slot', 1)
        return f"Error inesperado al intentar reservar el gimnasio: {str(e)}"

ALL_TOOLS_LIST = [external_rag_search_tool, check_gym_availability, book_gym_slot] 