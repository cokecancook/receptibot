# Guía de Uso del Agente

Este documento explica cómo utilizar el agente y describe los principales componentes que conforman su funcionalidad.

## Visión General

El agente está diseñado para procesar prompts, interactuar con herramientas y proporcionar respuestas inteligentes. La lógica principal se distribuye en varios módulos, cada uno responsable de un aspecto específico del comportamiento del agente.

## Componentes

### 1. `src/agents/api/main.py`
Este es el punto de entrada para la API del agente. Expone un endpoint (a través de Flask) que permite a clientes externos interactuar con el agente.

### 2. `src/agents/modules/agent.py`
Este módulo contiene la lógica principal del propio agente. Define la clase principal del agente, que gestiona el estado, maneja los prompts entrantes y coordina el uso de herramientas y prompts. Aquí es donde se implementan los procesos de razonamiento y toma de decisiones del agente.

### 3. `src/agents/modules/prompt.py`
Este módulo es responsable de la gestión de prompts. Define cómo se construyen, analizan y procesan los prompts. Incluye plantillas y lógica para manejar diferentes tipos de entrada del usuario.

### 4. `src/agents/modules/tools.py`
Este módulo define las herramientas que el agente puede utilizar para realizar diversas tareas. Las herramientas incluyen funciones para buscar, recuperar información e interactuar con sistemas externos. El agente utiliza estas herramientas para ampliar sus capacidades y proporcionar respuestas más completas.

## Cómo Usar

A. **Probar la API:**
    Para ejecutar una prueba automatizada y verificar que la API funciona correctamente, ejecuta:
    ```bash
    python src/agents/api/test_api.py
    ```

    Sustituye el contenido del mensaje por el prompt que desees. La respuesta contendrá la contestación del agente.

B. **Realizar una solicitud externa a la API:**
    Una vez que el servidor esté en funcionamiento (en http://localhost:8081), puedes interactuar con el agente usando una herramienta como `curl` o Postman. Por ejemplo, para enviar un prompt al agente:
    
    ```bash
    curl -X POST http://localhost:8081/chat -H "Content-Type: application/json" -d '{"prompt": "¡Hola, agente!"}'
    ```
    
    Sustituye `"¡Hola, agente!"` por el prompt que desees. La respuesta contendrá la contestación del agente.

## Notas Adicionales
- Para más detalles sobre cada módulo, consulta los docstrings y comentarios dentro de los archivos correspondientes.
- Puedes extender las capacidades del agente agregando nuevas herramientas a `tools.py` o modificando la lógica de prompt en `prompt.py`. 