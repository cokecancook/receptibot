# Mock Booking API

Este proyecto es una **API REST** en Python (Flask + SQLAlchemy) que simula un sistema de reservas para servicios de un hotel (por ejemplo, gimnasio y sauna).

---

## Tabla de contenidos

- [Mock Booking API](#mock-booking-api)
  - [Tabla de contenidos](#tabla-de-contenidos)
  - [Características](#características)
  - [Requisitos](#requisitos)
  - [Variables de entorno](#variables-de-entorno)
  - [Instalación y ejecución](#instalación-y-ejecución)
  - [Docker \& Docker Compose](#docker--docker-compose)
  - [Endpoints](#endpoints)
    - [`POST /availability`](#post-availability)
    - [`POST /booking`](#post-booking)
  - [Ejemplos de uso](#ejemplos-de-uso)
  - [Cómo funciona por dentro](#cómo-funciona-por-dentro)

---

## Características

* Generación de datos de prueba (*mock*) con Faker (nombres internacionales en ASCII y romanizados)
* Control de capacidad por slot horario
* Lógica de ocupación diaria con probabilidades de días completos o parciales
* Reconexión automática a la base de datos (retries)
* Endpoints para consultar disponibilidad y crear reservas

---

## Requisitos

* Python 3.11+
* PostgreSQL 12+ (u otro RDBMS soportado por SQLAlchemy)
* Docker & Docker Compose (opcional, para contenedores)

---

## Variables de entorno

Ejemplo de archivo `.env`:

```ini
DATABASE_URL=postgresql://usuario:password@postgres:5432/dbname
TOTAL_GUESTS=100              # (opcional) número fijo de reservas a generar
MAX_FILL_RATE=0.5             # (opcional) tasa máxima de ocupación parcial
FULL_DAY_PROB=0.2             # (opcional) probabilidad de día totalmente lleno
```

* **DATABASE\_URL**: URL de conexión para SQLAlchemy. Obligatorio.
* **TOTAL\_GUESTS**: (opcional) si se define, genera exactamente este número de reservas.
* **MAX\_FILL\_RATE**: (opcional) porcentaje máximo (0–1) de ocupación cuando no es día completo.
* **FULL\_DAY\_PROB**: (opcional) probabilidad (0–1) de que un día esté al 100%.

---

## Instalación y ejecución

1. Clona este repositorio:

   ```bash
   git clone https://tu-repo.git
   cd tu-repo
   ```

2. Crea y activa un entorno virtual:

   ```bash
   python -m venv venv
   source venv/bin/activate            # Linux / macOS
   venv\\Scripts\\activate.bat       # Windows
   ```

3. Instala dependencias:

   ```bash
   pip install -r requirements.txt
   ```

4. Exporta las variables de entorno (o usa un `.env`):

   ```bash
   export DATABASE_URL="postgresql://..."
   export TOTAL_GUESTS=200
   ```

5. Ejecuta la API:

   ```bash
   python app.py
   ```

La aplicación arrancará en `http://localhost:8000`.

---

## Docker & Docker Compose

Si prefieres contenedores:

1. Construye la imagen:

   ```bash
   docker build -t mock-booking-api .
   ```

2. Levanta con Docker Compose:

   ```bash
   docker-compose up -d
   ```

Este comando arrancará:

* Un contenedor `postgres` configurado con la base de datos.
* Un contenedor `api` con la aplicación Flask.

Para ver logs:

```bash
docker-compose logs -f
```

---

## Endpoints

### `POST /availability`

Devuelve la disponibilidad de un servicio en función del campo `start_time` en el body. Según el formato:

* Si `start_time` incluye hora (`YYYY-MM-DDThh:mm:ss`), devuelve **solo** ese slot.
* Si `start_time` es solo fecha (`YYYY-MM-DD`), devuelve las **3 primeras** franjas del día (08:00, 09:00 y 10:00).

**Request**:

* Método: POST
* Content-Type: `application/json`
* Body:

  ```json
  {
    "service_name": "sauna",
    "start_time": "2025-06-17"         // ó "2025-06-17T08:00:00"
  }
  ```

**Response 200**:

```json
[
  {
    "slot_id": 42,
    "start_time": "2025-06-17T08:00:00",
    "total_capacity": 3,
    "current_bookings": 1,
    "available_slots": 2
  },
  ...
]
```

**Errores**:

* 400: JSON mal formado o formato de `start_time` inválido.
* 404: servicio no válido.

### `POST /booking`

Crea una nueva reserva en un slot.

* **Request**:

  * Content-Type: `application/json`
  * Body:

    ```json
    {
      "slot_id": 42,
      "guest_name": "María García"
    }
    ```

* **Response 201**:

  ```json
  {
    "id": 137,
    "slot_id": 42,
    "guest_name": "María García"
  }
  ```

* **Errores**:

  * 400: JSON mal formado.
  * 422: validación Pydantic.
  * 404: el `slot_id` no existe.
  * 409: slot completo.

---

## Ejemplos de uso

**Disponibilidad de gimnasio**:

```bash
curl -X POST http://localhost:8000/availability \
     -H "Content-Type: application/json" \
     -d '{"service_name":"gimnasio","day":"2025-06-18"}'
```

**Crear reserva**:

```bash
curl -X POST http://localhost:8000/booking \
     -H "Content-Type: application/json" \
     -d '{"slot_id":55,"guest_name":"John Doe"}'
```

---

## Cómo funciona por dentro

1. **Arranque**: `get_session()` reintenta la conexión a la BBDD antes de fallar.
2. **Generación de datos**: al inicio, el script crea tablas, servicios, slots y booking mock.
3. **Locales Faker**: nombres occidentales + romanizados asiáticos para legibilidad.
4. **Persistencia**: SQLAlchemy + Postgres gestionan datos.
5. **API**: Flask expone endpoints y usa Pydantic para validaciones.

---

¡Con esto tienes todo lo necesario para usar e integrar la API de reservas mock!
