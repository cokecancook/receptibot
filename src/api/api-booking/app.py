from datetime import date
from typing import Optional

from flask import Flask, request, jsonify
from pydantic import BaseModel, Field, validator, ValidationError

from generator.main import Room, Reservation, get_session

app = Flask(__name__)


class AvailabilityQuery(BaseModel):
    checkin: date = Field(..., example="2025-07-01")
    checkout: date = Field(..., example="2025-07-05")
    room_type: Optional[str] = Field(None, example="double")

    @validator("checkout")
    def checkout_after_checkin(cls, v, values):
        if "checkin" in values and v <= values["checkin"]:
            raise ValueError("La fecha de checkout debe ser posterior al checkin")
        return v


class ReservationIn(BaseModel):
    guest_name: str = Field(..., example="Juan Pérez")
    checkin: date = Field(..., example="2025-07-01")
    checkout: date = Field(..., example="2025-07-05")
    room_id: Optional[int] = Field(
        None,
        description="Si se omite, el sistema asignará la primera habitación disponible",
    )
    room_type: Optional[str] = Field(None, description="Obligatorio si omites room_id")

    @validator("checkout")
    def checkout_after_checkin(cls, v, values):
        if "checkin" in values and v <= values["checkin"]:
            raise ValueError("La fecha de checkout debe ser posterior al checkin")
        return v

    @validator("room_type", always=True)
    def room_type_required_if_no_id(cls, v, values):
        if not values.get("room_id") and v is None:
            raise ValueError("Debes proporcionar room_type si no especificas room_id")
        return v


def get_db():
    return get_session()


def _available_rooms(
    db, checkin: date, checkout: date, room_type: Optional[str] = None
):
    q_rooms = db.query(Room)
    if room_type:
        q_rooms = q_rooms.filter(Room.type == room_type)

    occupied = (
        db.query(Reservation.room_id)
        .filter(Reservation.checkin < checkout, Reservation.checkout > checkin)
        .subquery()
    )

    return q_rooms.filter(~Room.id.in_(occupied)).all()


def room_to_dict(room):
    return {
        "id": room.id,
        "number": room.number,
        "type": room.type,
        "price": room.price,
    }


def reservation_to_dict(reservation):
    return {
        "id": reservation.id,
        "room_id": reservation.room_id,
        "guest_name": reservation.guest_name,
        "checkin": reservation.checkin.isoformat(),
        "checkout": reservation.checkout.isoformat(),
    }


@app.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify({"error": "Validation error", "details": e.errors()}), 400


@app.errorhandler(ValueError)
def handle_value_error(e):
    return jsonify({"error": str(e)}), 400


@app.route("/availability", methods=["POST"])
def availability():
    db = get_db()
    try:
        try:
            payload = AvailabilityQuery(**request.json)
        except ValidationError as e:
            return jsonify({"error": "Validation error", "details": e.errors()}), 400

        rooms = _available_rooms(
            db, payload.checkin, payload.checkout, payload.room_type
        )

        rooms_data = [room_to_dict(room) for room in rooms]

        return jsonify(rooms_data), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/reserve", methods=["POST"])
def reserve():
    db = get_db()
    try:
        try:
            payload = ReservationIn(**request.json)
        except ValidationError as e:
            return jsonify({"error": "Validation error", "details": e.errors()}), 400

        if payload.room_id:
            room = db.query(Room).filter(Room.id == payload.room_id).first()
            if not room:
                return jsonify({"error": "Habitación no encontrada"}), 404

            available = _available_rooms(db, payload.checkin, payload.checkout)
            if room not in available:
                return jsonify({"error": "Habitación no disponible en ese rango"}), 409
        else:
            available = _available_rooms(
                db, payload.checkin, payload.checkout, payload.room_type
            )
            if not available:
                return (
                    jsonify(
                        {
                            "error": "No hay habitaciones disponibles con ese tipo y rango"
                        }
                    ),
                    409,
                )
            room = available[0]

        # Crear reserva
        reservation = Reservation(
            room_id=room.id,
            guest_name=payload.guest_name,
            checkin=payload.checkin,
            checkout=payload.checkout,
        )
        db.add(reservation)
        db.commit()
        db.refresh(reservation)

        return jsonify(reservation_to_dict(reservation)), 201

    except Exception as e:
        db.rollback()
        return jsonify({"error": "Internal server error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "Hotel Barceló API"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
