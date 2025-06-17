import os
import logging
from pathlib import Path
from typing import List, Dict, Any
import requests
import json
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import PyPDF2
import hashlib
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self, 
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 ollama_host: str = "localhost",
                 ollama_port: int = 11434,
                 collection_name: str = "documents",
                 embedding_model: str = "nomic-embed-text:latest"):
        
        self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.ollama_url = f"http://{ollama_host}:{ollama_port}"
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        
        # Crear colección si no existe
        self._create_collection()
    
    def _create_collection(self):
        """Crear colección en Qdrant si no existe"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                # Obtener dimensión del modelo de embeddings
                test_embedding = self._get_embedding("test")
                vector_size = len(test_embedding)
                
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                    
                )
                logger.info(f"Colección '{self.collection_name}' creada con dimensión {vector_size}")
            else:
                logger.info(f"Colección '{self.collection_name}' ya existe")
        except Exception as e:
            logger.error(f"Error creando colección: {e}")
            raise
    
    def _get_embedding(self, text: str) -> List[float]:
        """Obtener embedding usando Ollama"""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={
                    "model": self.embedding_model,
                    "prompt": text
                },
                timeout=60  # Aumentado timeout para modelos grandes
            )
            response.raise_for_status()
            
            result = response.json()
            return result["embedding"]
        except Exception as e:
            logger.error(f"Error obteniendo embedding: {e}")
            raise
    
    def _extract_text_from_pdf(self, file_path: Path) -> str:
        """Extraer texto de archivo PDF"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            logger.error(f"Error extrayendo texto de PDF {file_path}: {e}")
            return ""
    
    def _extract_text_from_txt(self, file_path: Path) -> str:
        """Extraer texto de archivo TXT"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read().strip()
        except UnicodeDecodeError:
            # Intentar con diferentes encodings
            encodings = ['latin-1', 'cp1252', 'iso-8859-1']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as file:
                        return file.read().strip()
                except UnicodeDecodeError:
                    continue
            logger.error(f"No se pudo decodificar el archivo {file_path}")
            return ""
    
    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Dividir texto en chunks con overlap"""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Si no es el último chunk, buscar un buen punto de corte
            if end < len(text):
                # Buscar el último espacio o punto antes del final
                for i in range(end, start + chunk_size - 100, -1):
                    if text[i] in [' ', '.', '\n', '!', '?']:
                        end = i + 1
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - overlap
            
            if start >= len(text):
                break
        
        return chunks
    
    def _generate_document_id(self, file_path: Path, chunk_index: int) -> str:
        """Generar ID único para el documento"""
        content = f"{file_path.name}_{chunk_index}_{file_path.stat().st_mtime}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def process_document(self, file_path: Path) -> bool:
        """Procesar un documento individual"""
        try:
            logger.info(f"Procesando: {file_path.name}")
            
            # Extraer texto según el tipo de archivo
            if file_path.suffix.lower() == '.pdf':
                text = self._extract_text_from_pdf(file_path)
            elif file_path.suffix.lower() == '.txt':
                text = self._extract_text_from_txt(file_path)
            else:
                logger.warning(f"Tipo de archivo no soportado: {file_path.suffix}")
                return False
            
            if not text:
                logger.warning(f"No se pudo extraer texto de {file_path.name}")
                return False
            
            # Dividir en chunks
            chunks = self._chunk_text(text)
            logger.info(f"Documento dividido en {len(chunks)} chunks")
            
            # Procesar cada chunk
            points = []
            for i, chunk in enumerate(chunks):
                try:
                    # Generar embedding
                    logger.info(f"Generando embedding para chunk {i+1}/{len(chunks)}")
                    embedding = self._get_embedding(chunk)
                    
                    # Crear point para Qdrant
                    point_id = self._generate_document_id(file_path, i)
                    
                    point = PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "filename": file_path.name,
                            "file_path": str(file_path),
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "text": chunk,
                            "file_type": file_path.suffix.lower(),
                            "processed_at": int(time.time())
                        }
                    )
                    points.append(point)
                    
                    logger.info(f"✅ Chunk {i+1}/{len(chunks)} procesado")
                    
                except Exception as e:
                    logger.error(f"Error procesando chunk {i}: {e}")
                    continue
            
            # Insertar en Qdrant
            if points:
                self.qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=points
                )
                logger.info(f"✅ {file_path.name} procesado exitosamente ({len(points)} chunks)")
                return True
            else:
                logger.error(f"No se pudieron crear points para {file_path.name}")
                return False
                
        except Exception as e:
            logger.error(f"Error procesando {file_path.name}: {e}")
            return False
    
    def process_documents_folder(self, documents_path: Path):
        """Procesar todos los documentos en la carpeta"""
        if not documents_path.exists():
            logger.error(f"La carpeta {documents_path} no existe")
            return
        
        # Obtener todos los archivos PDF y TXT
        files = list(documents_path.glob("*.pdf")) + list(documents_path.glob("*.txt"))
        
        if not files:
            logger.warning("No se encontraron archivos PDF o TXT para procesar")
            return
        
        logger.info(f"Encontrados {len(files)} archivos para procesar")
        
        successful = 0
        failed = 0
        
        for file_path in files:
            if self.process_document(file_path):
                successful += 1
            else:
                failed += 1
        
        logger.info(f"Procesamiento completado: {successful} exitosos, {failed} fallidos")

def main():
    qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    ollama_host = os.getenv("OLLAMA_HOST", "ollama")
    ollama_port = int(os.getenv("OLLAMA_PORT", "11434"))
    collection_name = os.getenv("COLLECTION_NAME", "documents")
    embedding_model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
    
    logger.info("🚀 Iniciando procesador de documentos...")
    logger.info(f"📊 Qdrant: {qdrant_host}:{qdrant_port}")
    logger.info(f"🤖 Ollama: {ollama_host}:{ollama_port}")
    logger.info(f"🧠 Modelo de embeddings: {embedding_model}")
    
    max_retries = 20
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔍 Verificando conexión a Qdrant (intento {attempt + 1}/{max_retries})")
            qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
            qdrant_client.get_collections()
            logger.info("✅ Conexión a Qdrant establecida")
            
            # Verificar Ollama
            logger.info(f"🔍 Verificando conexión a Ollama (intento {attempt + 1}/{max_retries})")
            response = requests.get(f"http://{ollama_host}:{ollama_port}/api/tags", timeout=10)
            response.raise_for_status()
            
            models = response.json()
            model_names = [model['name'] for model in models.get('models', [])]
            if embedding_model not in model_names:
                logger.warning(f"⚠️ Modelo {embedding_model} no encontrado. Modelos disponibles: {model_names}")
                if model_names:
                    logger.info(f"🔄 Usando el primer modelo disponible: {model_names[0]}")
                    embedding_model = model_names[0]
                else:
                    raise Exception("No hay modelos disponibles en Ollama")
            
            logger.info("✅ Conexión a Ollama establecida")
            logger.info(f"📋 Modelos disponibles: {model_names}")
            break
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"❌ Intento {attempt + 1}/{max_retries} fallido: {e}")
                logger.info(f"⏳ Reintentando en {retry_delay} segundos...")
                time.sleep(retry_delay)
            else:
                logger.error("💥 No se pudo conectar a los servicios después de varios intentos")
                return
    
    processor = DocumentProcessor(
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        ollama_host=ollama_host,
        ollama_port=ollama_port,
        collection_name=collection_name,
        embedding_model=embedding_model
    )
    
    documents_path = Path("/app/documents")
    processor.process_documents_folder(documents_path)
    
    logger.info("🎉 Procesamiento completado")

if __name__ == "__main__":
    main()