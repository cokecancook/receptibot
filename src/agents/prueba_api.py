import requests
import json
import uuid

# URL de tu agent_api.py (FastAPI)
AGENT_API_URL = "http://localhost:8001" # Asegúrate que este sea el puerto correcto

def send_message_to_agent(message: str, thread_id: str):
    """
    Envía un mensaje al agente y devuelve la respuesta.
    """
    endpoint = f"{AGENT_API_URL}/chat/{thread_id}"
    payload = {"message": message}
    headers = {"Content-Type": "application/json"}

    print(f"👤 Tú (Thread: {thread_id}): {message}")

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=60) # Timeout aumentado
        response.raise_for_status() # Lanza una excepción para errores HTTP (4xx o 5xx)
        
        agent_response = response.json()
        reply = agent_response.get("reply", "El agente no devolvió un 'reply'.")
        print(f"🤖 Agente (Thread: {thread_id}): {reply}\n")
        return agent_response
        
    except requests.exceptions.HTTPError as http_err:
        print(f"❌ Error HTTP: {http_err}")
        print(f"   Respuesta del servidor: {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"❌ Error de Conexión: {conn_err}")
        print(f"   Asegúrate de que agent_api.py esté ejecutándose en {AGENT_API_URL}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"❌ Error de Timeout: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"❌ Error en la Petición: {req_err}")
    except json.JSONDecodeError:
        print(f"❌ Error decodificando JSON. Respuesta del servidor: {response.text}")
    
    print("-" * 30)
    return None

def run_conversation():
    """
    Ejecuta una conversación de ejemplo con el agente.
    """
    # Genera un ID de hilo único para esta conversación
    # Puedes usar un ID fijo si quieres continuar una conversación específica entre ejecuciones del notebook,
    # siempre y cuando el MemorySaver del agente siga activo y no se haya reiniciado la agent_api.py.
    conversation_thread_id = f"notebook-test-{uuid.uuid4().hex[:8]}"
    print(f"--- Iniciando conversación con Thread ID: {conversation_thread_id} ---")

    # Caso 1: Pregunta general (debería usar external_rag_search_tool)
    send_message_to_agent("Hola, ¿qué tipo de desayuno ofrecen?", conversation_thread_id)

    # Caso 2: Pregunta sobre el gimnasio (debería usar check_gym_availability)
    # Suponiendo que la fecha actual es válida para el ejemplo.
    # Podrías querer generar una fecha dinámicamente, ej: (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00")
    send_message_to_agent("¿Hay sitio en el gimnasio para el 2025-07-20?", conversation_thread_id)
    
    # Caso 3: El usuario quiere reservar (después de ver disponibilidad)
    # El agente podría haber respondido con los horarios disponibles.
    # Ahora el usuario confirma un slot específico y da su nombre.
    # Nota: La respuesta del agente al paso anterior es crucial aquí.
    # Esta simulación asume que el agente ofrecerá un slot y pedirá confirmación/nombre.
    send_message_to_agent("Reserva en el gimnasio a las 8:00 del 2025-06-25 a nombre de John Doe", conversation_thread_id)

    # Caso 4: Si el agente pidió el nombre por separado
    # send_message_to_agent("Mi nombre es Ana López.", conversation_thread_id)

    # Caso 5: Pregunta sin sentido para ver cómo responde
    send_message_to_agent("¿De qué color son las nubes cuando llueve chocolate?", conversation_thread_id)

    print(f"--- Fin de la conversación (Thread ID: {conversation_thread_id}) ---")

if __name__ == "__main__":
    # Primero, verificar si el servicio del agente está disponible
    try:
        health_response = requests.get(f"{AGENT_API_URL}/agent-health", timeout=5)
        if health_response.status_code == 200:
            print(f"✅ API del Agente está activa: {health_response.json()}")
            print("-" * 30)
            run_conversation()
        else:
            print(f"⚠️ API del Agente respondió con estado {health_response.status_code}: {health_response.text}")
    except requests.ConnectionError:
        print(f"❌ No se pudo conectar a la API del Agente en {AGENT_API_URL}.")
        print("   Asegúrate de que agent_api.py (FastAPI) se esté ejecutando en el puerto 8001.")
        print("   Y que tu servicio RAG (Flask en app.py) también esté ejecutándose en el puerto 8080.")
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado al verificar la salud del agente: {e}")