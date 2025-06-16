FROM ollama/ollama:latest

# Instalar dependencias necesarias
RUN apt-get update && apt-get install -y \
    jq \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar script de inicialización
COPY ollama-init.sh /ollama-init.sh
RUN chmod +x /ollama-init.sh

# Variables de entorno por defecto
ENV OLLAMA_ORIGINS=*
ENV MODELS_TO_DOWNLOAD="nomic-embed-text,all-minilm,llama3.2:1b"

EXPOSE 11434

ENTRYPOINT ["/ollama-init.sh"]