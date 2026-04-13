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
    from datetime import datetime

    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Plan nie istnieje")

    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Tylko pliki .xlsx")

    contents = file.file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents))
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    has_date = 'Data' in headers

    db.query(Event).filter(
        Event.schedule_id == schedule_id,
        Event.type == "zajecia"
    ).delete()

    added = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:
            continue

        if has_date:
            przedmiot, dzien, data, od, do_, sala, prowadzacy, uwagi = (list(row) + [None] * 8)[:8]
        else:
            przedmiot, dzien, od, do_, sala, prowadzacy, uwagi = (list(row) + [None] * 7)[:7]
            data = None

        date_obj = None
        if data:
            if isinstance(data, str):
                try:
                    date_obj = datetime.strptime(data, '%Y-%m-%d')
                except ValueError:
                    pass
            elif hasattr(data, 'year'):
                date_obj = datetime(data.year, data.month, data.day)

        event = Event(
            type="zajecia",
            title=str(przedmiot) if przedmiot else None,
            day_of_week=str(dzien).lower().strip() if dzien else None,
            date=date_obj,
            time_start=str(od) if od else None,
            time_end=str(do_) if do_ else None,
            location=str(sala) if sala else None,
            lecturer=str(prowadzacy) if prowadzacy else None,
            notes=str(uwagi) if uwagi else None,
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

@router.post("/schedules/{schedule_id}/import-ics")
async def import_ics(schedule_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    import re
    from datetime import datetime, timedelta

    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Plan nie istnieje")

    content = (await file.read()).decode('utf-8')
    warsaw_offset = timedelta(hours=2)

    SKROTY = {
        'Gk': 'Grafika komputerowa',
        'Iwpp GJ': 'Informatyka w procesach produkcyjnych',
        'Iwpp PG': 'Informatyka w procesach produkcyjnych',
        'Prir': 'Programowanie równoległe i rozproszone',
        'Prir - AK': 'Programowanie równoległe i rozproszone - projekt AK',
        'Ps': 'Programowanie systemowe',
        'Smiw': 'Systemy mikroprocesorowe i wbudowane',
        'Smiw w': 'Systemy mikroprocesorowe i wbudowane',
        'Taiib': 'Tworzenie aplikacji internetowych i bazodanowych',
        'Taiib - P': 'Tworzenie aplikacji internetowych i bazodanowych - projekt',
        'Wtp': 'Współczesne techniki programowania',
        'WPP': 'Wizualizacja procesów przemysłowych',
        'WPP - GK': 'Wizualizacja procesów przemysłowych - projekt GK',
        'IO': 'Inżynieria oprogramowania',
    }

    days_pl = {0: 'poniedziałek', 1: 'wtorek', 2: 'środa',
               3: 'czwartek', 4: 'piątek', 5: 'sobota', 6: 'niedziela'}

    blocks = content.split('BEGIN:VEVENT')[1:]
    added = 0
    skipped = 0

    for block in blocks:
        summary_match = re.search(r'SUMMARY:(.*?)(?:\r\n|\n)', block)
        start_match = re.search(r'DTSTART:(\d{8}T\d{6}Z)', block)
        end_match = re.search(r'DTEND:(\d{8}T\d{6}Z)', block)

        if not (summary_match and start_match and end_match):
            continue

        summary = summary_match.group(1).strip()
        if 'Wakacje' in summary or 'test zdalny' in summary.lower():
            skipped += 1
            continue

        dt_start = datetime.strptime(start_match.group(1), '%Y%m%dT%H%M%SZ') + warsaw_offset
        dt_end = datetime.strptime(end_match.group(1), '%Y%m%dT%H%M%SZ') + warsaw_offset

        existing = db.query(Event).filter(
            Event.schedule_id == schedule_id,
            Event.date == dt_start.replace(hour=0, minute=0, second=0, microsecond=0),
            Event.time_start == dt_start.strftime('%H:%M')
        ).first()
        if existing:
            skipped += 1
            continue

        parts = summary.split()
        type_idx = -1
        for i, p in enumerate(parts):
            if p in ['wyk', 'lab', 'proj', 'sem', 'w']:
                type_idx = i
                break

        if type_idx >= 0:
            skrot = ' '.join(parts[:type_idx])
            rest = parts[type_idx+1:]
        else:
            skrot = summary
            rest = []

        prowadzacy = ''
        sala_parts = rest
        if rest and len(rest[0]) <= 5 and rest[0][0].isupper():
            prowadzacy = rest[0]
            sala_parts = rest[1:]

        sala = ' '.join(sala_parts).strip()
        przedmiot = SKROTY.get(skrot, skrot)

        event = Event(
            type=detect_type(summary),
            title=przedmiot,
            date=dt_start.replace(hour=0, minute=0, second=0, microsecond=0),
            day_of_week=days_pl[dt_start.weekday()],
            time_start=dt_start.strftime('%H:%M'),
            time_end=dt_end.strftime('%H:%M'),
            location=sala,
            lecturer=prowadzacy,
            schedule_id=schedule_id
        )
        db.add(event)
        added += 1

    db.commit()
    return {"added": added, "skipped": skipped}


def detect_type(summary: str) -> str:
    summary_lower = summary.lower()
    if 'egzamin' in summary_lower or 'test' in summary_lower:
        return 'egzamin'
    elif 'proj' in summary_lower:
        return 'projekt'
    elif 'wyk' in summary_lower:
        return 'wykład'
    elif 'lab' in summary_lower:
        return 'laboratorium'
    elif 'online' in summary_lower or 'zdaln' in summary_lower:
        return 'online'
    elif 'cwicz' in summary_lower or 'ćwicz' in summary_lower:
        return 'ćwiczenia'
    else:
        return 'zajecia'