import os
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from app.database import SessionLocal
from app.models import User, Schedule, Event
from app.services.claude import ask_claude

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def get_or_create_user(db, telegram_chat_id: str) -> User:
    user = db.query(User).filter(User.telegram_chat_id == str(telegram_chat_id)).first()
    if not user:
        user = User(telegram_chat_id=str(telegram_chat_id))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_schedule_context_for_user(db, user: User) -> str:
    if not user.schedule_id:
        return "Brak przypisanego planu zajęć."

    events = db.query(Event).filter(
        Event.schedule_id == user.schedule_id,
        Event.type == "zajecia",
        Event.is_cancelled == False
    ).all()

    if not events:
        return "Brak zajęć w planie."

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
        user = get_or_create_user(db, chat_id)

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
                    await update.message.reply_text(f"Przypisano plan: {schedule.name}. Możesz teraz pytać o zajęcia.")
                    return
                else:
                    await update.message.reply_text("Nie znaleziono planu o tym numerze.")
                    return

            if schedules:
                schedule_list = "\n".join([f"{s.id}. {s.name}" for s in schedules])
                await update.message.reply_text(
                    f"Najpierw wybierz plan zajęć wpisując jego numer:\n\n{schedule_list}"
                )
            else:
                await update.message.reply_text("Brak planów w systemie. Skontaktuj się z administratorem.")
            return

        schedule_context = get_schedule_context_for_user(db, user)
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