from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Schedule, Event
import openpyxl
import io
from app.models import Schedule, Event, Lecturer
from pydantic import BaseModel
from typing import Optional
router = APIRouter()

DAYS_MAP = {
    "poniedziałek": 0, "wtorek": 1, "środa": 2,
    "czwartek": 3, "piątek": 4, "sobota": 5, "niedziela": 6
}


@router.post("/schedules")
def create_schedule(name: str, db: Session = Depends(get_db)):
    schedule = Schedule(name=name)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return {"id": schedule.id, "name": schedule.name}


@router.get("/schedules")
def list_schedules(db: Session = Depends(get_db)):
    schedules = db.query(Schedule).all()
    return [{"id": s.id, "name": s.name} for s in schedules]


@router.post("/schedules/{schedule_id}/upload")
def upload_schedule(schedule_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Plan nie istnieje")

    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Tylko pliki .xlsx")

    contents = file.file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents))
    ws = wb.active

    db.query(Event).filter(
        Event.schedule_id == schedule_id,
        Event.type == "zajecia"
    ).delete()

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
            schedule_id=schedule_id
        )
        db.add(event)
        added += 1

    db.commit()
    return {"message": f"Dodano {added} zajęć do planu {schedule.name}"}


class LecturerCreate(BaseModel):
    abbreviation: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    room: Optional[str] = None
    phone: Optional[str] = None
    office_hours: Optional[str] = None


@router.post("/lecturers")
def create_lecturer(data: LecturerCreate, db: Session = Depends(get_db)):
    existing = db.query(Lecturer).filter(
        Lecturer.abbreviation == data.abbreviation
    ).first()
    if existing:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    lecturer = Lecturer(**data.model_dump())
    db.add(lecturer)
    db.commit()
    db.refresh(lecturer)
    return lecturer


@router.get("/lecturers")
def list_lecturers(db: Session = Depends(get_db)):
    return db.query(Lecturer).all()


@router.get("/lecturers/{abbreviation}")
def get_lecturer(abbreviation: str, db: Session = Depends(get_db)):
    lecturer = db.query(Lecturer).filter(
        Lecturer.abbreviation == abbreviation
    ).first()
    if not lecturer:
        raise HTTPException(status_code=404, detail="Prowadzący nie znaleziony")
    return lecturer