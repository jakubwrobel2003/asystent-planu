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

    query = db.query(Event).filter(
        Event.schedule_id == user.schedule_id,
        Event.type == "zajecia",
        Event.is_cancelled == False
    )

    intent_type = intent.get("type")
    day = intent.get("day")
    subject = intent.get("subject")

    if intent_type == "day":
        if day:
            query = query.filter(Event.day_of_week == day)
        else:
            tomorrow = (datetime.now().weekday() + 1) % 7
            day_name = [k for k, v in DAYS_MAP.items() if v == tomorrow][0]
            query = query.filter(Event.day_of_week == day_name)
    elif intent_type == "subject" and subject:
        query = query.filter(Event.title.ilike(f"%{subject}%"))
    elif intent_type == "lecturer":
        lecturer = intent.get("lecturer")
        if lecturer:
            query = query.filter(Event.lecturer.ilike(f"%{lecturer}%"))
        if day:
            query = query.filter(Event.day_of_week == day)
    events = query.order_by(Event.time_start).all()

    if not events:
        return "Brak zajęć spełniających kryteria."

    lines = []
    for e in events:
        lines.append(
            f"{e.title} | {e.day_of_week} | {e.time_start}-{e.time_end} | {e.location} | {e.lecturer}"
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