from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class Lecturer(Base):
    __tablename__ = "lecturers"

    id = Column(Integer, primary_key=True, index=True)
    abbreviation = Column(String, unique=True, nullable=False)  # "KaG"
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    room = Column(String, nullable=True)        # "pok. 215 bud. A"
    phone = Column(String, nullable=True)
    office_hours = Column(String, nullable=True) # "wt 10:00-11:00"
    created_at = Column(DateTime, default=datetime.utcnow)

    events = relationship("Event", back_populates="lecturer_obj")
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_chat_id = Column(String, unique=True, nullable=True)
    whatsapp_number = Column(String, unique=True, nullable=True)
    email = Column(String, nullable=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)
    schedule = relationship("Schedule", back_populates="users")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    polsl_sid = Column(String, nullable=True)
    semester = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="schedule")
    events = relationship("Event", back_populates="schedule")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    day_of_week = Column(String, nullable=True)
    date = Column(DateTime, nullable=True)
    time_start = Column(String, nullable=True)
    time_end = Column(String, nullable=True)
    location = Column(String, nullable=True)
    lecturer = Column(String, nullable=True)           # skrót — zostaje dla kompatybilności
    lecturer_id = Column(Integer, ForeignKey("lecturers.id"), nullable=True)  # nowe
    lecturer_obj = relationship("Lecturer", back_populates="events")
    notes = Column(String, nullable=True)
    is_cancelled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)
    schedule = relationship("Schedule", back_populates="events")