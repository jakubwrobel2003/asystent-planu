import os
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from sqlalchemy import or_, and_

from app.database import SessionLocal
from app.models import User, Schedule, Event, Lecturer, EventType
from app.services.claude import ask_claude, classify_intent

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

DAYS_MAP = {
    "poniedziałek": 0, "wtorek": 1, "środa": 2,
    "czwartek": 3, "piątek": 4, "sobota": 5, "niedziela": 6,
}
DAYS_LIST = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]


def get_or_create_user(db, telegram_chat_id: str) -> User:
    user = db.query(User).filter(User.telegram_chat_id == str(telegram_chat_id)).first()
    if not user:
        user = User(telegram_chat_id=str(telegram_chat_id))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def parse_relative_date(message: str):
    """
    Rozpoznaje: dziś/dzisiaj, jutro, pojutrze, wczoraj, za N dni/dzień.
    Zwraca datetime albo None.
    """
    m = message.lower().strip()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if "pojutrze" in m:
        return today + timedelta(days=2)
    if "jutro" in m:
        return today + timedelta(days=1)
    if "wczoraj" in m:
        return today - timedelta(days=1)
    if "dzisiaj" in m or re.search(r"\bdzi[sś]\b", m):
        return today

    match = re.search(r"za\s+(\d+)\s+(dni|dzień|dni[eę])", m)
    if match:
        n = int(match.group(1))
        return today + timedelta(days=n)

    # "w poniedziałek", "na wtorek", "we środę" - znajdź najbliższy taki dzień
    # Obsługuję też odmiany: poniedziałek/poniedziałku, środa/środę/środy itd.
    day_forms = {
        0: ["poniedziałek", "poniedziałku"],
        1: ["wtorek", "wtorku"],
        2: ["środa", "środę", "środy", "środzie"],
        3: ["czwartek", "czwartku"],
        4: ["piątek", "piątku"],
        5: ["sobota", "sobotę", "soboty", "sobocie"],
        6: ["niedziela", "niedzielę", "niedzieli"],
    }
    for day_num, forms in day_forms.items():
        if any(f in m for f in forms):
            days_ahead = day_num - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return today + timedelta(days=days_ahead)

    return None


def filter_events_for_date(query, target: datetime):
    """
    Pasuje do obu trybów:
    - Event.date = konkretna data (ICS)
    - Event.day_of_week = tylko dzień (XLSX)
    """
    start = target.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    day_name = DAYS_LIST[target.weekday()]

    return query.filter(
        or_(
            and_(Event.date >= start, Event.date < end),
            and_(Event.date.is_(None), Event.day_of_week == day_name),
        )
    )


def get_filtered_context(db, user: User, intent: dict, raw_message: str = "") -> str:
    if not user.schedule_id:
        return "Brak przypisanego planu zajęć."

    # Najpierw spróbuj rozpoznać datę bezpośrednio z wiadomości - to nie strzela
    relative = parse_relative_date(raw_message) if raw_message else None

    query = db.query(Event).filter(
        Event.schedule_id == user.schedule_id,
        Event.is_cancelled == False,  # noqa: E712
    )

    intent_type = intent.get("type")
    intent_date = intent.get("date")
    day = intent.get("day")
    subject = intent.get("subject")
    lecturer = intent.get("lecturer")

    if intent_type == "lecturer_info":
        if lecturer:
            lect = db.query(Lecturer).filter(
                Lecturer.abbreviation.ilike(f"%{lecturer}%")
            ).first()
            if lect:
                parts = [f"Prowadzący: {lect.abbreviation}"]
                if lect.first_name or lect.last_name:
                    parts.append(f"Imię i nazwisko: {lect.first_name or ''} {lect.last_name or ''}".strip())
                if lect.email:
                    parts.append(f"Email: {lect.email}")
                if lect.room:
                    parts.append(f"Gabinet: {lect.room}")
                if lect.office_hours:
                    parts.append(f"Dyżury: {lect.office_hours}")
                return "\n".join(parts)
        return "Brak danych o prowadzącym."

    # Priorytet: parse_relative_date > intent.date > intent.day
    target_date = relative
    if not target_date and intent_date:
        try:
            target_date = datetime.strptime(intent_date, "%Y-%m-%d")
        except ValueError:
            target_date = None

    if intent_type == "day" or relative is not None:
        if target_date:
            query = filter_events_for_date(query, target_date)
        elif day:
            query = query.filter(Event.day_of_week == day)

    elif intent_type == "week":
        base = target_date
        if not base and intent_date:
            try:
                base = datetime.strptime(intent_date, "%Y-%m-%d")
            except ValueError:
                base = None
        if base:
            monday = (base - timedelta(days=base.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sunday_end = monday + timedelta(days=7)
            query = query.filter(
                or_(
                    and_(Event.date >= monday, Event.date < sunday_end),
                    Event.date.is_(None),
                )
            )

    elif intent_type == "subject" and subject:
        query = query.filter(Event.title.ilike(f"%{subject}%"))

    elif intent_type == "lecturer":
        if lecturer:
            query = query.filter(Event.lecturer.ilike(f"%{lecturer}%"))
        if day:
            query = query.filter(Event.day_of_week == day)

    events = query.order_by(Event.date, Event.time_start).all()
    if not events:
        if target_date:
            return f"Brak zajęć na {target_date.strftime('%d.%m.%Y')} ({DAYS_LIST[target_date.weekday()]})."
        return "Brak zajęć spełniających kryteria."

    lines = []
    for e in events:
        date_str = e.date.strftime("%d.%m") if e.date else (e.day_of_week or "-")
        lines.append(
            f"{date_str} ({e.day_of_week or '-'}) | {e.title} | {e.time_start}-{e.time_end} | {e.location} | {e.lecturer}"
        )
    return "\n".join(lines)


# ----- Command handlers -----

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        chat_id = str(update.message.chat_id)
        get_or_create_user(db, chat_id)

        schedules = db.query(Schedule).all()
        if not schedules:
            await update.message.reply_text(
                "Witaj! Nie ma jeszcze żadnych planów w systemie. "
                "Administrator musi najpierw dodać plan zajęć."
            )
            return

        schedule_list = "\n".join([f"{s.id}. {s.name}" for s in schedules])
        await update.message.reply_text(
            "Witaj! Dostępne komendy:\n"
            "/plany - lista planów\n"
            "/zmien - zmień swój plan\n"
            "/moj - pokaż obecnie wybrany plan\n\n"
            f"Wybierz swój plan zajęć wpisując jego numer:\n\n{schedule_list}"
        )
    finally:
        db.close()


async def handle_plany(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        schedules = db.query(Schedule).all()
        if not schedules:
            await update.message.reply_text("Brak planów w systemie.")
            return
        schedule_list = "\n".join([f"{s.id}. {s.name}" for s in schedules])
        await update.message.reply_text(f"Dostępne plany:\n\n{schedule_list}")
    finally:
        db.close()


async def handle_moj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        chat_id = str(update.message.chat_id)
        user = get_or_create_user(db, chat_id)
        if not user.schedule_id:
            await update.message.reply_text(
                "Nie masz jeszcze wybranego planu. Użyj /plany i wpisz jego numer."
            )
            return
        schedule = db.query(Schedule).filter(Schedule.id == user.schedule_id).first()
        if not schedule:
            await update.message.reply_text(
                "Twój zapisany plan już nie istnieje. Użyj /plany aby wybrać nowy."
            )
            return
        await update.message.reply_text(
            f"Twój aktualny plan: {schedule.id}. {schedule.name}"
        )
    finally:
        db.close()


async def handle_zmien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        chat_id = str(update.message.chat_id)
        user = get_or_create_user(db, chat_id)

        # /zmien 4  -> zmiana od razu
        if context.args:
            arg = context.args[0].strip()
            if arg.isdigit():
                schedule = db.query(Schedule).filter(Schedule.id == int(arg)).first()
                if not schedule:
                    await update.message.reply_text("Nie znaleziono planu o tym numerze.")
                    return
                user.schedule_id = schedule.id
                db.commit()
                await update.message.reply_text(f"Zmieniono plan na: {schedule.name}.")
                return

        # /zmien bez argumentu - odblokuj tryb wyboru
        user.schedule_id = None
        db.commit()
        schedules = db.query(Schedule).all()
        if not schedules:
            await update.message.reply_text("Brak planów w systemie.")
            return
        schedule_list = "\n".join([f"{s.id}. {s.name}" for s in schedules])
        await update.message.reply_text(
            f"Wybierz nowy plan wpisując jego numer:\n\n{schedule_list}"
        )
    finally:
        db.close()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        chat_id = str(update.message.chat_id)
        message = update.message.text or ""
        user = get_or_create_user(db, chat_id)

        # Tryb wyboru planu
        if not user.schedule_id:
            schedules = db.query(Schedule).all()
            if message.strip().isdigit():
                schedule = db.query(Schedule).filter(Schedule.id == int(message.strip())).first()
                if schedule:
                    user.schedule_id = schedule.id
                    db.commit()
                    await update.message.reply_text(f"Przypisano plan: {schedule.name}.")
                    return
                await update.message.reply_text("Nie znaleziono planu o tym numerze.")
                return

            if schedules:
                schedule_list = "\n".join([f"{s.id}. {s.name}" for s in schedules])
                await update.message.reply_text(
                    f"Wybierz plan zajęć wpisując jego numer:\n\n{schedule_list}"
                )
            else:
                await update.message.reply_text("Brak planów w systemie.")
            return

        await context.bot.send_chat_action(
            chat_id=update.message.chat_id,
            action="typing",
        )

        intent = classify_intent(message)
        schedule_context = get_filtered_context(db, user, intent, raw_message=message)
        result = ask_claude(message, schedule_context)

        if result.get("action"):
            from app.routers.chat import apply_action
            apply_action(result["action"], db, user.schedule_id)

        await update.message.reply_text(result["text"])
    finally:
        db.close()


def create_app():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Brak TELEGRAM_BOT_TOKEN w środowisku")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("plany", handle_plany))
    application.add_handler(CommandHandler("zmien", handle_zmien))
    application.add_handler(CommandHandler("moj", handle_moj))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application