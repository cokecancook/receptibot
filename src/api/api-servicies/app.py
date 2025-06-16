from datetime import date, datetime, time

from flask import Flask, request, jsonify
from pydantic import BaseModel, ValidationError
from sqlalchemy import func

from generator.main import get_session, Service, Slot, Booking


app = Flask(__name__)


class BookingCreate(BaseModel):
    slot_id: int
    guest_name: str


@app.route("/<string:service_name>/availability", methods=["GET"])
def get_service_availability(service_name):

    if service_name not in ["gimnasio", "sauna"]:
        return (
            jsonify({"error": "Servicio no encontrado. Pruebe 'gimnasio' o 'sauna'."}),
            404,
        )

    day_str = request.args.get("day")
    if not day_str:
        return (
            jsonify({"error": "El parámetro 'day' (YYYY-MM-DD) es obligatorio."}),
            400,
        )

    try:
        day = date.fromisoformat(day_str)
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD."}), 400

    start_of_day = datetime.combine(day, time(hour=8))
    end_of_day = datetime.combine(day, time(hour=21))

    session = get_session()
    try:
        bookings_count_subq = (
            session.query(func.count(Booking.id))
            .filter(Booking.slot_id == Slot.id)
            .scalar_subquery()
        ).label("bookings_count")

        slots_with_bookings = (
            session.query(Slot, bookings_count_subq)
            .join(Service)
            .filter(Service.name == service_name)
            .filter(Slot.start_time >= start_of_day)
            .filter(Slot.start_time < end_of_day)
            .order_by(Slot.start_time)
            .all()
        )

        availability_list = []
        for slot, bookings_count in slots_with_bookings:
            available_slots = slot.capacity - (bookings_count or 0)
            availability_list.append(
                {
                    "slot_id": slot.id,
                    "start_time": slot.start_time.isoformat(),
                    "total_capacity": slot.capacity,
                    "current_bookings": bookings_count or 0,
                    "available_slots": available_slots,
                }
            )

        return jsonify(availability_list), 200

    finally:
        session.close()


@app.route("/booking", methods=["POST"])
def create_booking():

    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo de la petición debe ser JSON."}), 400

    try:
        booking_data = BookingCreate.model_validate(json_data)
    except ValidationError as e:
        return (
            jsonify({"error": "Datos de entrada inválidos", "details": e.errors()}),
            422,
        )  # Unprocessable Entity

    session = get_session()
    try:
        slot_to_book = (
            session.query(Slot)
            .filter(Slot.id == booking_data.slot_id)
            .with_for_update()
            .first()
        )

        if not slot_to_book:
            return jsonify({"error": "La franja horaria (slot) no existe."}), 404

        current_bookings = (
            session.query(Booking).filter(Booking.slot_id == slot_to_book.id).count()
        )

        if current_bookings >= slot_to_book.capacity:
            return (
                jsonify({"error": "No hay huecos disponibles en esta franja horaria."}),
                409,
            )  # Conflict

        new_booking = Booking(
            slot_id=booking_data.slot_id, guest_name=booking_data.guest_name
        )

        session.add(new_booking)
        session.commit()

        response_data = {
            "id": new_booking.id,
            "slot_id": new_booking.slot_id,
            "guest_name": new_booking.guest_name,
        }
        return jsonify(response_data), 201

    except Exception as e:
        session.rollback()
        return (
            jsonify({"error": "Ha ocurrido un error interno.", "details": str(e)}),
            500,
        )
    finally:
        session.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
