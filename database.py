# database.py
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = "sqlite:///./booking_bot.db"  # Файл базы данных будет создан в той же директории

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}) # check_same_thread for SQLite
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Определяем модели таблиц (сущности из нашего плана)

class Provider(Base):
    __tablename__ = "providers"

    provider_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    services = relationship("Service", back_populates="provider")

class Service(Base):
    __tablename__ = "services"

    service_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    provider_id = Column(Integer, ForeignKey("providers.provider_id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    price = Column(Float, nullable=True) # Можно сделать REAL если нужно точнее

    provider = relationship("Provider", back_populates="services")
    time_slots = relationship("TimeSlot", back_populates="service", cascade="all, delete-orphan")

class TimeSlot(Base):
    __tablename__ = "time_slots"

    slot_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    service_id = Column(Integer, ForeignKey("services.service_id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False) # Рассчитывается при создании
    is_available = Column(Boolean, default=True)

    service = relationship("Service", back_populates="time_slots")
    booking = relationship("Booking", back_populates="slot", uselist=False, cascade="all, delete-orphan") # Один слот - одно бронирование

class Booking(Base):
    __tablename__ = "bookings"

    booking_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    slot_id = Column(Integer, ForeignKey("time_slots.slot_id"), unique=True, nullable=False) # Слот может быть забронирован только один раз
    client_telegram_id = Column(Integer, nullable=False)
    booking_timestamp = Column(DateTime, default=datetime.datetime.utcnow) # Время по UTC
    status = Column(String, default="confirmed") # e.g., 'confirmed', 'cancelled_by_client', 'cancelled_by_provider'

    slot = relationship("TimeSlot", back_populates="booking")


def create_db_tables():
    """Создает все таблицы в базе данных."""
    Base.metadata.create_all(bind=engine)

# Удобная функция для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    # Этот блок выполнится, если запустить файл database.py напрямую
    # (например, python database.py)
    # Он создаст таблицы в базе данных.
    print("Creating database tables...")
    create_db_tables()
    print("Database tables created successfully (if they didn't exist).")