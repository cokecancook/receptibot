# 🏨 Hotel Barceló API

Una API REST completa para gestión de reservas hoteleras desarrollada con Flask y SQLAlchemy.

## 📋 Tabla de Contenidos

- [Características](#-características)
- [Instalación](#-instalación)
- [Configuración](#-configuración)
- [Uso](#-uso)
- [Endpoints](#-endpoints)
- [Ejemplos Prácticos](#-ejemplos-prácticos)
- [Manejo de Errores](#-manejo-de-errores)
- [Estructura de Datos](#-estructura-de-datos)

## ✨ Características

- **Consulta de disponibilidad** de habitaciones por fechas y tipo
- **Creación de reservas** con asignación automática o manual de habitaciones
- **Validaciones robustas** de fechas, tipos de habitación y datos de entrada
- **Prevención de conflictos** evitando reservas solapadas
- **Monitoreo de salud** con estadísticas de la base de datos
- **Manejo completo de errores** con mensajes informativos

## 🚀 Instalación

### Requisitos

- Python 3.8+
- SQLAlchemy
- Flask
- Pydantic
- Faker (para el generador de datos)

### Instalación de dependencias

```bash
pip install flask sqlalchemy pydantic faker
```

### Estructura del proyecto

```
hotel-api/
├── generador.py    # Generador de datos y modelos
├── api.py          # API Flask principal
└── README.md       # Este archivo
```

## ⚙️ Configuración

### 1. Configurar Base de Datos

Configura la variable de entorno `DATABASE_URL`:

```bash
# SQLite (recomendado para desarrollo)
export DATABASE_URL="sqlite:///hotel.db"

# PostgreSQL (producción)
export DATABASE_URL="postgresql://usuario:password@localhost/hotel_db"

# MySQL
export DATABASE_URL="mysql+pymysql://usuario:password@localhost/hotel_db"
```

### 2. Generar Datos de Prueba

Ejecuta el generador para crear habitaciones y reservas de ejemplo:

```bash
python generador.py
```

Esto creará:
- **50 habitaciones** con números del 001 al 050
- **100 reservas** aleatorias con nombres generados por Faker
- **3 tipos de habitación**: single (€80), double (€120), suite (€200)

### 3. Iniciar la API

```bash
python api.py
```

La API estará disponible en: `http://localhost:8000`

## 🎯 Uso

### Estados de Respuesta HTTP

| Código | Descripción |
|--------|-------------|
| `200`  | Consulta exitosa |
| `201`  | Reserva creada exitosamente |
| `400`  | Datos de entrada inválidos |
| `404`  | Recurso no encontrado |
| `409`  | Conflicto (habitación no disponible) |
| `500`  | Error interno del servidor |
| `503`  | Servicio no disponible |

## 📡 Endpoints

### 1. GET /health - Estado de la API

Verifica el estado de la API y estadísticas de la base de datos.

**Request:**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "Hotel Barceló API",
  "database": "connected",
  "database_url": "sqlite:///hotel.db",
  "stats": {
    "total_rooms": 50,
    "total_reservations": 100,
    "room_types": {
      "single": 18,
      "double": 16,
      "suite": 16
    }
  }
}
```

### 2. POST /availability - Consultar Disponibilidad

Consulta habitaciones disponibles para un rango de fechas específico.

**Request:**
```bash
curl -X POST http://localhost:8000/availability \
  -H "Content-Type: application/json" \
  -d '{
    "checkin": "2025-12-01",
    "checkout": "2025-12-05",
    "room_type": "double"
  }'
```

**Parámetros:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `checkin` | string (date) | ✅ | Fecha de entrada (YYYY-MM-DD) |
| `checkout` | string (date) | ✅ | Fecha de salida (YYYY-MM-DD) |
| `room_type` | string | ❌ | Tipo: "single", "double", "suite" |

**Response:**
```json
{
  "available_rooms": [
    {
      "id": 5,
      "number": "005",
      "type": "double",
      "price": 120.0
    },
    {
      "id": 12,
      "number": "012",
      "type": "double", 
      "price": 120.0
    }
  ],
  "total_available": 2,
  "search_criteria": {
    "checkin": "2025-12-01",
    "checkout": "2025-12-05",
    "room_type": "double",
    "nights": 4
  }
}
```

### 3. POST /reserve - Crear Reserva

Crea una nueva reserva. Puede especificar una habitación concreta o dejar que el sistema asigne automáticamente.

**Request (Asignación Automática):**
```bash
curl -X POST http://localhost:8000/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "guest_name": "Ana García",
    "checkin": "2025-12-01",
    "checkout": "2025-12-05",
    "room_type": "suite"
  }'
```

**Request (Habitación Específica):**
```bash
curl -X POST http://localhost:8000/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "guest_name": "Carlos Ruiz",
    "checkin": "2025-12-01", 
    "checkout": "2025-12-05",
    "room_id": 25
  }'
```

**Parámetros:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `guest_name` | string | ✅ | Nombre del huésped (2-100 caracteres) |
| `checkin` | string (date) | ✅ | Fecha de entrada (no puede ser pasada) |
| `checkout` | string (date) | ✅ | Fecha de salida (posterior al checkin) |
| `room_id` | integer | ❌ | ID específico de habitación |
| `room_type` | string | ❌* | Tipo si no se especifica room_id |

*Requerido si `room_id` no se proporciona.

**Response:**
```json
{
  "reservation": {
    "id": 101,
    "room_id": 25,
    "guest_name": "Ana García",
    "checkin": "2025-12-01",
    "checkout": "2025-12-05"
  },
  "room_details": {
    "id": 25,
    "number": "025",
    "type": "suite",
    "price": 200.0
  },
  "nights": 4,
  "total_cost": 800.0
}
```

## 💡 Ejemplos Prácticos

### Ejemplo 1: Buscar habitaciones disponibles para fin de semana

```bash
# Consultar habitaciones para el fin de semana
curl -X POST http://localhost:8000/availability \
  -H "Content-Type: application/json" \
  -d '{
    "checkin": "2025-12-14",
    "checkout": "2025-12-16"
  }'
```

### Ejemplo 2: Reserva familiar (suite)

```bash
# Reservar una suite para familia
curl -X POST http://localhost:8000/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "guest_name": "Familia Rodríguez",
    "checkin": "2025-12-20",
    "checkout": "2025-12-27",
    "room_type": "suite"
  }'
```

### Ejemplo 3: Reserva de habitación específica

```bash
# Primero consultar disponibilidad
curl -X POST http://localhost:8000/availability \
  -H "Content-Type: application/json" \
  -d '{
    "checkin": "2025-12-01",
    "checkout": "2025-12-03",
    "room_type": "single"
  }'

# Luego reservar habitación específica (usando ID del resultado anterior)
curl -X POST http://localhost:8000/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "guest_name": "Pedro Martín",
    "checkin": "2025-12-01",
    "checkout": "2025-12-03",
    "room_id": 7
  }'
```

## ⚠️ Manejo de Errores

### Errores de Validación (400)

```json
{
  "error": "Datos de entrada inválidos",
  "details": [
    {
      "loc": ["checkout"],
      "msg": "La fecha de checkout debe ser posterior al checkin",
      "type": "value_error"
    }
  ]
}
```

### Habitación No Disponible (409)

```json
{
  "error": "No hay habitaciones disponibles",
  "requested_type": "suite",
  "dates": "2025-12-24 - 2025-12-26"
}
```

### Habitación No Encontrada (404)

```json
{
  "error": "Habitación no encontrada"
}
```

## 📊 Estructura de Datos

### Modelo Room (Habitación)

```python
{
  "id": 1,           # ID único
  "number": "001",   # Número de habitación 
  "type": "single",  # Tipo: single/double/suite
  "price": 80.0      # Precio por noche en euros
}
```

### Modelo Reservation (Reserva)

```python
{
  "id": 1,                    # ID único de reserva
  "room_id": 1,              # ID de la habitación
  "guest_name": "Juan Pérez", # Nombre del huésped
  "checkin": "2025-12-01",   # Fecha entrada
  "checkout": "2025-12-05"   # Fecha salida
}
```

### Tipos de Habitación y Precios

| Tipo | Precio/Noche | Descripción |
|------|--------------|-------------|
| `single` | €80 | Habitación individual |
| `double` | €120 | Habitación doble |
| `suite` | €200 | Suite de lujo |

## 🛠️ Desarrollo

### Ejecutar en modo desarrollo

```bash
# Con recarga automática
python api.py

# La API se reiniciará automáticamente al detectar cambios
```

### Variables de entorno

```bash
# Configuración de base de datos
export DATABASE_URL="sqlite:///hotel.db"

# Habilitar modo debug (opcional) 
export FLASK_DEBUG=1
```

### Logs y Debug

La API muestra información útil al iniciarse:

```
🏨 Iniciando Hotel Barceló API...
📊 Base de datos: sqlite:///hotel.db
🌐 Endpoints disponibles:
   POST /availability - Consultar disponibilidad  
   POST /reserve - Crear reserva
   GET  /health - Estado de la API
```

## 📝 Notas Importantes

1. **Fechas**: Todas las fechas deben estar en formato ISO (YYYY-MM-DD)
2. **Solapamientos**: La API previene automáticamente reservas solapadas
3. **Validaciones**: No se permiten checkins en fechas pasadas
4. **Asignación**: Si no especificas `room_id`, se asigna la primera habitación disponible
5. **Transacciones**: Todas las operaciones de base de datos son transaccionales

## 🚀 Próximos Pasos

- [ ] Autenticación y autorización
- [ ] Cancelación de reservas  
- [ ] Modificación de reservas existentes
- [ ] Búsqueda avanzada con filtros de precio
- [ ] API de reportes y estadísticas
- [ ] Integración con sistemas de pago

---

**¿Necesitas ayuda?** Revisa el endpoint `/health` para verificar el estado de la API y la conectividad de la base de datos.