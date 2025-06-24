# TFM-Deusens

Este proyecto implementa un agente conversacional basado en Python, utilizando Docker para facilitar la gestión de dependencias y entornos.

## Requisitos previos

- [Docker](https://www.docker.com/get-started)
- [Python 3.8+](https://www.python.org/downloads/)
- [pip](https://pip.pypa.io/en/stable/installation/)

## Instrucciones de inicio

Sigue estos pasos para poner en marcha el agente conversacional:

### 1. Levantar los servicios con Docker

Desde la raíz del proyecto, ejecuta:

```bash
docker compose up --build
```

Esto construirá y levantará los servicios definidos en el archivo `docker-compose.yml`.

### 2. Crear y activar un entorno virtual

Crea un entorno virtual en Python para aislar las dependencias:

```bash
python -m venv venv
```

Activa el entorno virtual:

- En Windows:
    ```bash
    .\venv\Scripts\activate
    ```
- En macOS/Linux:
    ```bash
    source venv/bin/activate
    ```

### 3. Instalar dependencias del agente

Navega a la carpeta del agente:

```bash
cd src/agents
```

Instala los requisitos:

```bash
pip install -r requirements.txt
```

### 4. Iniciar el agente conversacional

Ejecuta el agente:

```bash
python tool_agent.py
```

## Estructura del proyecto

```
TFM-Deusens/
├── docker-compose.yml
├── src/
│   └── agents/
│       ├── tool_agent.py
│       └── requirements.txt
└── README.md
```

## Uso

Una vez iniciado, el agente conversacional estará listo para recibir y procesar mensajes según la lógica definida en `tool_agent.py`.

## Notas

- Asegúrate de tener Docker y Python correctamente instalados.
- Si tienes problemas con dependencias, revisa las versiones especificadas en `requirements.txt`.
- Para detener los servicios Docker, usa `docker compose down`.

---