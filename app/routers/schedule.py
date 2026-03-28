from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event
from datetime import datetime, date
import openpyxl
import io

router = APIRouter()

DAYS_MAP = {
    "poniedziałek": 0,
    "wtorek": 1,
    "środa": 2,
    "czwartek": 3,
    "piątek": 4,
    "sobota": 5,
    "niedziela": 6
}


@router.post("/upload")
def upload_schedule(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Tylko pliki .xlsx")

    contents = file.file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents))
    ws = wb.active

    db.query(Event).filter(Event.type == "zajecia").delete()

    added = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:
            continue

        event = Event(
            type="zajecia",
            title=row[0],
            day_of_week=row[1].lower().strip() if row[1] else None,
            time_start=str(row[2]) if row[2] else None,
            time_end=str(row[3]) if row[3] else None,
            location=row[4] if row[4] else None,
            lecturer=row[5] if row[5] else None,
            notes=row[6] if row[6] else None,
        )
        db.add(event)
        added += 1

    db.commit()
    return {"message": f"Dodano {added} zajęć"}


@router.get("/tomorrow")
def get_tomorrow(db: Session = Depends(get_db)):
    tomorrow = datetime.now()
    tomorrow_weekday = tomorrow.weekday()

    day_name = [k for k, v in DAYS_MAP.items() if v == tomorrow_weekday]
    if not day_name:
        return {"zajecia": []}

    events = db.query(Event).filter(
        Event.type == "zajecia",
        Event.day_of_week == day_name[0],
        Event.is_cancelled == False
    ).order_by(Event.time_start).all()

    return {
        "dzien": day_name[0],
        "zajecia": [
            {
                "przedmiot": e.title,
                "od": e.time_start,
                "do": e.time_end,
                "sala": e.location,
                "prowadzący": e.lecturer,
                "uwagi": e.notes
            }
            for e in events
        ]
    }


@router.get("/week")
def get_week(db: Session = Depends(get_db)):
    events = db.query(Event).filter(
        Event.type == "zajecia",
        Event.is_cancelled == False
    ).all()

    week = {day: [] for day in DAYS_MAP.keys()}

    for e in events:
        if e.day_of_week in week:
            week[e.day_of_week].append({
                "przedmiot": e.title,
                "od": e.time_start,
                "do": e.time_end,
                "sala": e.location,
                "prowadzący": e.lecturer
            })

    return week