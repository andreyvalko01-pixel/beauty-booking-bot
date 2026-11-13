from datetime import datetime, time
from pathlib import Path

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import settings

if settings.database_url.startswith("sqlite"):
    Path(settings.database_url.split("///")[-1]).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    duration: Mapped[int] = mapped_column(Integer)   # хвилини
    price: Mapped[int] = mapped_column(Integer)


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    specialty: Mapped[str] = mapped_column(String(100))
    google_calendar_id: Mapped[str | None] = mapped_column(String(200))

    schedule: Mapped[list["WorkDay"]] = relationship(lazy="selectin", cascade="all, delete-orphan")
    services: Mapped[list[Service]] = relationship(secondary="master_services", lazy="selectin")


class MasterService(Base):
    __tablename__ = "master_services"

    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), primary_key=True)


class WorkDay(Base):
    """Графік майстра: день тижня (0 = понеділок) і години роботи."""

    __tablename__ = "work_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"))
    weekday: Mapped[int] = mapped_column(Integer)
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    # pending_payment -> confirmed -> done / cancelled
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    prepaid: Mapped[int] = mapped_column(Integer, default=0)
    reminded_day: Mapped[bool] = mapped_column(default=False)
    reminded_2h: Mapped[bool] = mapped_column(default=False)
    google_event_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    client: Mapped[Client] = relationship(lazy="selectin")
    master: Mapped[Master] = relationship(lazy="selectin")
    service: Mapped[Service] = relationship(lazy="selectin")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
