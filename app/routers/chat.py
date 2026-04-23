from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import Event, Schedule, EventType
from app.services.claude import ask_claude

router = APIRouter()


class ChatMessage(BaseModel):
    message: str
    schedule_id: Optional[int] = None


def get_schedule_context(db: Session, schedule_id: Optional[int] = None) -> str:
    query = db.query(Event).filter(
        Event.type == EventType.zajecia,
        Event.is_cancelled == False,  # noqa: E712
    )
    if schedule_id:
        query = query.filter(Event.schedule_id == schedule_id)

    events = query.all()
    if not events:
        return "Brak zajęć w bazie."

    lines = []
    for e in events:
        lines.append(
            f"{e.title} | {e.day_of_week} | {e.time_start}-{e.time_end} | {e.location} | {e.lecturer}"
        )
    return "\n".join(lines)


def apply_action(action: dict, db: Session, schedule_id: Optional[int] = None) -> Optional[str]:
    """
    Wykonuje akcję zwróconą przez Claude. Zwraca krótki komunikat o tym co się stało
    albo None, jeśli nie znaleziono pasującego eventu.
    """
    act = action.get("action")
    title = action.get("title")

    if act == "cancel":
        query = db.query(Event).filter(Event.title.ilike(f"%{title}%"))
        if schedule_id:
            query = query.filter(Event.schedule_id == schedule_id)
        if action.get("day_of_week"):
            query = query.filter(Event.day_of_week == action["day_of_week"])
        event = query.first()
        if not event:
            return None
        event.is_cancelled = True
        db.commit()
        return f"Odwołano: {event.title} ({event.day_of_week or '-'})"

    if act == "update":
        query = db.query(Event).filter(Event.title.ilike(f"%{title}%"))
        if schedule_id:
            query = query.filter(Event.schedule_id == schedule_id)
        if action.get("day_of_week") and not any(
            k in action for k in ("time_start", "time_end", "location", "notes")
        ):
            # jeżeli jedyną zmianą ma być dzień, nie filtruj po starym dniu
            pass
        event = query.first()
        if not event:
            return None

        for field in ("day_of_week", "time_start", "time_end", "location", "notes"):
            if action.get(field):
                setattr(event, field, action[field])
        db.commit()
        return f"Zaktualizowano: {event.title}"

    if act == "add":
        event = Event(
            type=EventType.zajecia,
            title=title,
            day_of_week=action.get("day_of_week"),
            time_start=action.get("time_start"),
            time_end=action.get("time_end"),
            location=action.get("location"),
            notes=action.get("notes"),
            schedule_id=schedule_id,
        )
        db.add(event)
        db.commit()
        return f"Dodano: {title}"

    return None


@router.post("/")
def chat(msg: ChatMessage, db: Session = Depends(get_db)):
    # Jeśli podano schedule_id, zwaliduj
    if msg.schedule_id:
        schedule = db.query(Schedule).filter(Schedule.id == msg.schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Plan nie istnieje")

    context = get_schedule_context(db, msg.schedule_id)
    result = ask_claude(msg.message, context)

    applied = None
    if result.get("action"):
        applied = apply_action(result["action"], db, msg.schedule_id)

    return {
        "response": result["text"],
        "applied": applied,
        "action": result.get("action"),
    }
