import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from app.database import SessionLocal
from app.models import User, Schedule, Event
from app.services.claude import ask_claude, classify_intent

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

DAYS_MAP = {
    "poniedziałek": 0, "wtorek": 1, "środa": 2,
    "czwartek": 3, "piątek": 4, "sobota": 5, "niedziela": 6
}


def get_or_create_user(db, telegram_chat_id: str) -> User:
    user = db.query(User).filter(User.telegram_chat_id == str(telegram_chat_id)).first()
    if not user:
        user = User(telegram_chat_id=str(telegram_chat_id))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_filtered_context(db, user, intent: dict) -> str:
    if not user.schedule_id:
        return "Brak przypisanego planu zajęć."

    from datetime import datetime, date

    query = db.query(Event).filter(
        Event.schedule_id == user.schedule_id,
        Event.type == "zajecia",
        Event.is_cancelled == False
    )

    intent_type = intent.get("type")
    intent_date = intent.get("date")
    day = intent.get("day")
    subject = intent.get("subject")
    lecturer = intent.get("lecturer")

    if intent_type == "day":
        if intent_date:
            try:
                target_date = datetime.strptime(intent_date, '%Y-%m-%d').date()
                query = query.filter(
                    Event.date >= datetime(target_date.year, target_date.month, target_date.day),
                    Event.date < datetime(target_date.year, target_date.month, target_date.day, 23, 59)
                )
            except ValueError:
                if day:
                    query = query.filter(Event.day_of_week == day)
        elif day:
            query = query.filter(Event.day_of_week == day)

    elif intent_type == "week":
        if intent_date:
            try:
                target_date = datetime.strptime(intent_date, '%Y-%m-%d').date()
                week_start = datetime(target_date.year, target_date.month, target_date.day)
                from datetime import timedelta
                week_end = week_start + timedelta(days=7)
                query = query.filter(Event.date >= week_start, Event.date < week_end)
            except ValueError:
                pass

    elif intent_type == "subject" and subject:
        query = query.filter(Event.title.ilike(f"%{subject}%"))

    elif intent_type == "lecturer":
        if lecturer:
            query = query.filter(Event.lecturer.ilike(f"%{lecturer}%"))
        if day:
            query = query.filter(Event.day_of_week == day)

    elif intent_type == "lecturer_info":
        lecturer_abbr = intent.get("lecturer")
        if lecturer_abbr:
            from app.models import Lecturer
            lect = db.query(Lecturer).filter(
                Lecturer.abbreviation.ilike(f"%{lecturer_abbr}%")
            ).first()
            if lect:
                parts = [f"Prowadzący: {lect.abbreviation}"]
                if lect.first_name or lect.last_name:
                    parts.append(f"Imię i nazwisko: {lect.first_name} {lect.last_name}")
                if lect.email:
                    parts.append(f"Email: {lect.email}")
                if lect.room:
                    parts.append(f"Gabinet: {lect.room}")
                if lect.office_hours:
                    parts.append(f"Dyżury: {lect.office_hours}")
                return "\n".join(parts)
        return "Brak danych o prowadzącym."

    events = query.order_by(Event.date, Event.time_start).all()

    if not events:
        return "Brak zajęć spełniających kryteria."

    lines = []
    for e in events:
        date_str = e.date.strftime('%d.%m') if e.date else e.day_of_week
        lines.append(
            f"{date_str} ({e.day_of_week}) | {e.title} | {e.time_start}-{e.time_end} | {e.location} | {e.lecturer}"
        )
    return "\n".join(lines)


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
            f"Witaj! Wybierz swój plan zajęć wpisując jego numer:\n\n{schedule_list}"
        )
    finally:
        db.close()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        chat_id = str(update.message.chat_id)
        message = update.message.text
        user = get_or_create_user(db, chat_id)

        if not user.schedule_id:
            schedules = db.query(Schedule).all()
            if message.isdigit():
                schedule = db.query(Schedule).filter(Schedule.id == int(message)).first()
                if schedule:
                    user.schedule_id = schedule.id
                    db.commit()
                    await update.message.reply_text(f"Przypisano plan: {schedule.name}.")
                    return
                else:
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

        await update.message.reply_text("Sprawdzam plan...")
        await context.bot.send_chat_action(
            chat_id=update.message.chat_id,
            action="typing"
        )

        intent = classify_intent(message)
        schedule_context = get_filtered_context(db, user, intent)
        result = ask_claude(message, schedule_context)

        if result["action"]:
            from app.routers.chat import apply_action
            apply_action(result["action"], db, user.schedule_id)

        await update.message.reply_text(result["text"])
    finally:
        db.close()


def create_app():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application