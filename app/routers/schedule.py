from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.models import Event, Schedule, EventType

router = APIRouter()

DAYS_MAP = {
    "poniedziałek": 0,
    "wtorek": 1,
    "środa": 2,
    "czwartek": 3,
    "piątek": 4,
    "sobota": 5,
    "niedziela": 6,
}


def _require_schedule(db: Session, schedule_id: int) -> Schedule:
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Plan nie istnieje")
    return schedule


@router.get("/{schedule_id}/tomorrow")
def get_tomorrow(schedule_id: int, db: Session = Depends(get_db)):
    _require_schedule(db, schedule_id)

    tomorrow_weekday = (datetime.now().weekday() + 1) % 7
    day_name = next((k for k, v in DAYS_MAP.items() if v == tomorrow_weekday), None)
    if not day_name:
        return {"zajecia": []}

    events = db.query(Event).filter(
        Event.schedule_id == schedule_id,
        Event.type == EventType.zajecia,
        Event.day_of_week == day_name,
        Event.is_cancelled == False,  # noqa: E712
    ).order_by(Event.time_start).all()

    return {
        "dzien": day_name,
        "zajecia": [
            {
                "przedmiot": e.title,
                "od": e.time_start,
                "do": e.time_end,
                "sala": e.location,
                "prowadzący": e.lecturer,
                "uwagi": e.notes,
            }
            for e in events
        ],
    }


@router.get("/{schedule_id}/week")
def get_week(schedule_id: int, db: Session = Depends(get_db)):
    _require_schedule(db, schedule_id)

    events = db.query(Event).filter(
        Event.schedule_id == schedule_id,
        Event.type == EventType.zajecia,
        Event.is_cancelled == False,  # noqa: E712
    ).all()

    week = {day: [] for day in DAYS_MAP.keys()}
    for e in events:
        if e.day_of_week in week:
            week[e.day_of_week].append({
                "przedmiot": e.title,
                "od": e.time_start,
                "do": e.time_end,
                "sala": e.location,
                "prowadzący": e.lecturer,
            })

    return week
