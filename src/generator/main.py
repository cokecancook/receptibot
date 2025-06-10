import os
import random
from datetime import datetime, timedelta

from faker import Faker
from sqlalchemy import (
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


DB_URL = os.getenv("DATABASE_URL")

Base = declarative_base()
fake = Faker()

ROOM_TYPES = [
    ("single", 80.0),
    ("double", 120.0),
    ("suite", 200.0),
]


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True)
    number = Column(String, unique=True, nullable=False)
    type = Column(String, nullable=False)
    price = Column(Float, nullable=False)

    reservations = relationship(
        "Reservation", back_populates="room", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Room {self.number} ({self.type})>"


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    guest_name = Column(String, nullable=False)
    checkin = Column(Date, nullable=False)
    checkout = Column(Date, nullable=False)

    room = relationship("Room", back_populates="reservations")

    def __repr__(self) -> str:
        return (
            f"<Reservation {self.id}: {self.guest_name} en habitación {self.room_id} "
            f"({self.checkin}—{self.checkout})>"
        )


def get_session(db_url: str = DB_URL):

    engine = create_engine(db_url, echo=False, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def generate_rooms(session, total_rooms: int = 50):

    rooms = []
    for i in range(1, total_rooms + 1):
        room_type, price = random.choice(ROOM_TYPES)
        rooms.append(Room(number=f"{i:03d}", type=room_type, price=price))

    session.bulk_save_objects(rooms)
    session.commit()
    print(f"Generadas {len(rooms)} habitaciones.")


def generate_reservations(session, num_res: int = 100):

    room_ids = [r.id for r in session.query(Room.id).all()]
    if not room_ids:
        raise RuntimeError(
            "No hay habitaciones para asignar reservas. Ejecuta primero generate_rooms()."
        )

    reservations = []
    for _ in range(num_res):
        room_id = random.choice(room_ids)
        start = datetime.now() - timedelta(days=random.randint(0, 60))
        nights = random.randint(1, 7)
        reservations.append(
            Reservation(
                room_id=room_id,
                guest_name=fake.name(),
                checkin=start.date(),
                checkout=(start + timedelta(days=nights)).date(),
            )
        )

    session.bulk_save_objects(reservations)
    session.commit()
    print(f"Generadas {len(reservations)} reservas.")


def main():
    session = get_session()

    if not session.query(Room).first():
        generate_rooms(session, total_rooms=50)

    generate_reservations(session, num_res=100)
    session.close()

    print(f"Base de datos mock creada/actualizada en {DB_URL}.")


if __name__ == "__main__":
    main()
