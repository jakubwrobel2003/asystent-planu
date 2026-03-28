from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import Event
from app.services.claude import ask_claude
import json

router = APIRouter()


class ChatMessage(BaseModel):
    message: str


def get_schedule_context(db: Session) -> str:
    events = db.query(Event).filter(
        Event.type == "zajecia",
        Event.is_cancelled == False
    ).all()

    if not events:
        return "Brak zajęć w bazie."

    lines = []
    for e in events:
        lines.append(
            f"{e.title} | {e.day_of_week} | {e.time_start}-{e.time_end} | {e.location} | {e.lecturer}"
        )
    return "\n".join(lines)

def apply_action(action: dict, db):
    if action["action"] == "cancel":
        event = db.query(Event).filter(
            Event.title.ilike(f"%{action['title']}%"),
            Event.day_of_week == action.get("day_of_week")
        ).first()
        if event:
            event.is_cancelled = True
            db.commit()

    elif action["action"] == "update":
        event = db.query(Event).filter(
            Event.title.ilike(f"%{action['title']}%")
        ).first()
        if event:
            if action.get("day_of_week"):
                event.day_of_week = action["day_of_week"]
            if action.get("time_start"):
                event.time_start = action["time_start"]
            if action.get("time_end"):
                event.time_end = action["time_end"]
            if action.get("location"):
                event.location = action["location"]
            if action.get("notes"):
                event.notes = action["notes"]
            db.commit()

    elif action["action"] == "add":
        event = Event(
            type="zajecia",
            title=action["title"],
            day_of_week=action.get("day_of_week"),
            time_start=action.get("time_start"),
            time_end=action.get("time_end"),
            location=action.get("location"),
            notes=action.get("notes")
        )
        db.add(event)
        db.commit()
@router.post("/")
def chat(msg: ChatMessage, db: Session = Depends(get_db)):
    context = get_schedule_context(db)
    result = ask_claude(msg.message, context)

    if result["action"]:
        action = result["action"]

        if action["action"] == "cancel":
            event = db.query(Event).filter(
                Event.title.ilike(f"%{action['title']}%"),
                Event.day_of_week == action.get("day_of_week")
            ).first()
            if event:
                event.is_cancelled = True
                db.commit()

        elif action["action"] == "update":
            event = db.query(Event).filter(
                Event.title.ilike(f"%{action['title']}%")
            ).first()
            if event:
                if action.get("day_of_week"):
                    event.day_of_week = action["day_of_week"]
                if action.get("time_start"):
                    event.time_start = action["time_start"]
                if action.get("time_end"):
                    event.time_end = action["time_end"]
                if action.get("location"):
                    event.location = action["location"]
                if action.get("notes"):
                    event.notes = action["notes"]
                db.commit()

        elif action["action"] == "add":
            event = Event(
                type="zajecia",
                title=action["title"],
                day_of_week=action.get("day_of_week"),
                time_start=action.get("time_start"),
                time_end=action.get("time_end"),
                location=action.get("location"),
                notes=action.get("notes")
            )
            db.add(event)
            db.commit()

    return {"response": result["text"]}