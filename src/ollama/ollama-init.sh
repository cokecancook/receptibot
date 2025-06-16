#!/bin/bash
set -e

echo "🚀 Iniciando Ollama para Barceló Agent..."

# Iniciar Ollama en background
ollama serve &
OLLAMA_PID=$!

# Función para limpiar al salir
cleanup() {
    echo "🛑 Cerrando Ollama..."
    kill $OLLAMA_PID 2>/dev/null || true
    wait $OLLAMA_PID 2>/dev/null || true
}
trap cleanup EXIT

# Esperar a que Ollama esté listo
echo "⏳ Esperando a que Ollama esté disponible..."
while ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done

echo "✅ Ollama está listo"

# Parsear modelos a descargar
IFS=',' read -ra MODELS <<< "$MODELS_TO_DOWNLOAD"

# Verificar si los modelos ya están descargados
EXISTING_MODELS=$(curl -s http://localhost:11434/api/tags | jq -r '.models[]?.name // empty' 2>/dev/null || echo "")

for model in "${MODELS[@]}"; do
    model=$(echo "$model" | xargs)  # Limpiar espacios
    if echo "$EXISTING_MODELS" | grep -q "^$model"; then
        echo "✅ Modelo $model ya existe"
    else
        echo "📥 Descargando modelo $model..."
        if ollama pull "$model"; then
            echo "✅ Modelo $model descargado exitosamente"
        else
            echo "❌ Error descargando modelo $model"
        fi
    fi
done

echo "🎉 Setup completado. Modelos disponibles:"
ollama list

# Mantener Ollama ejecutándose
echo "🔄 Ollama ejecutándose en puerto 11434..."
wait $OLLAMA_PID