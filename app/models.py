from sqlalchemy import Column, Integer, String, DateTime, Boolean
from app.database import Base
from datetime import datetime


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)        # "zajecia", "egzamin", "termin", "inne"
    title = Column(String, nullable=False)       # "Matematyka", "Egzamin ze Statystyki"
    day_of_week = Column(String, nullable=True)  # "środa" — dla zajęć cyklicznych
    date = Column(DateTime, nullable=True)       # konkretna data — dla egzaminów, terminów
    time_start = Column(String, nullable=True)   # "10:00"
    time_end = Column(String, nullable=True)     # "11:30"
    location = Column(String, nullable=True)     # "sala 204, bud. A"
    lecturer = Column(String, nullable=True)     # "dr Kowalski"
    notes = Column(String, nullable=True)        # dodatkowe info
    is_cancelled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)