import os
import random
from datetime import datetime, timedelta
from collections import defaultdict

from faker import Faker
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DB_URL = os.getenv("DATABASE_URL")
TOTAL_GUESTS = os.getenv("TOTAL_GUESTS")
if TOTAL_GUESTS is not None:
    try:
        TOTAL_GUESTS = int(TOTAL_GUESTS)
    except ValueError:
        raise ValueError(
            "La variable de entorno TOTAL_GUESTS debe ser un entero válido."
        )

MAX_FILL_RATE = float(os.getenv("MAX_FILL_RATE", 0.5))
FULL_DAY_PROB = float(os.getenv("FULL_DAY_PROB", 0.2))

Base = declarative_base()
fake = Faker(
    [
        "es_ES",
        "en_US",
        "en_GB",
        "fr_FR",
        "de_DE"
    ]
)

offering = [
    {"name": "gimnasio", "capacity": 10},
    {"name": "sauna", "capacity": 3},
]


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    capacity = Column(Integer, nullable=False)

    slots = relationship("Slot", back_populates="service", cascade="all, delete-orphan")


class Slot(Base):
    __tablename__ = "slots"
    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    capacity = Column(Integer, nullable=False)

    service = relationship("Service", back_populates="slots")
    bookings = relationship(
        "Booking", back_populates="slot", cascade="all, delete-orphan"
    )


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=False)
    guest_name = Column(String, nullable=False)

    slot = relationship("Slot", back_populates="bookings")


def get_session(db_url: str = DB_URL):
    engine = create_engine(db_url, echo=False, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def generate_services(session):
    existing = {s.name for s in session.query(Service).all()}
    new_services = []
    for svc in offering:
        if svc["name"] not in existing:
            new_services.append(Service(name=svc["name"], capacity=svc["capacity"]))
    if new_services:
        session.bulk_save_objects(new_services)
        session.commit()
    print(f"Servicios generados/confirmados: {[s['name'] for s in offering]}")


def generate_slots(session, days_ahead: int = 7, open_hr: int = 6, close_hr: int = 22):
    services = session.query(Service).all()
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    slots = []
    for svc in services:
        for d in range(days_ahead):
            day = now + timedelta(days=d)
            for hr in range(open_hr, close_hr):
                slots.append(
                    Slot(
                        service_id=svc.id,
                        start_time=day.replace(hour=hr),
                        capacity=svc.capacity,
                    )
                )
    session.bulk_save_objects(slots)
    session.commit()
    print(f"Generados {len(slots)} slots para los próximos {days_ahead} días.")


def generate_bookings(session):
    slots = session.query(Slot).all()

    if TOTAL_GUESTS is not None:
        bookings = []
        for _ in range(TOTAL_GUESTS):
            slot = random.choice(slots)
            current = session.query(Booking).filter_by(slot_id=slot.id).count()
            if current < slot.capacity:
                bookings.append(Booking(slot_id=slot.id, guest_name=fake.name()))
        session.bulk_save_objects(bookings)
        session.commit()
        print(
            f"Generadas {len(bookings)} reservas totales especificadas (TOTAL_GUESTS={TOTAL_GUESTS})."
        )
        return

    days = defaultdict(list)
    for slot in slots:
        day_key = (slot.service_id, slot.start_time.date())
        days[day_key].append(slot)

    bookings = []
    for (svc_id, date), day_slots in days.items():
        if random.random() < FULL_DAY_PROB:
            fill_rate = 1.0
        else:
            fill_rate = random.uniform(0, MAX_FILL_RATE)
        for slot in day_slots:
            cap = slot.capacity
            num = random.randint(0, int(cap * fill_rate))
            for _ in range(num):
                bookings.append(Booking(slot_id=slot.id, guest_name=fake.name()))

    session.bulk_save_objects(bookings)
    session.commit()
    print(
        f"Generadas {len(bookings)} reservas de prueba con llenado diario basado en probabilidades."
    )


def main():
    session = get_session()
    generate_services(session)
    generate_slots(session)
    generate_bookings(session)
    session.close()
    print("Mock de datos de servicios creado/actualizado.")


if __name__ == "__main__":
    main()
