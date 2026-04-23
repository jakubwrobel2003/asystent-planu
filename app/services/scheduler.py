import asyncio
import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.models import Event, User, EventType

scheduler = BackgroundScheduler()

DAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]


def _tomorrow_events(db, schedule_id: int | None = None):
    tomorrow_weekday = (datetime.now().weekday() + 1) % 7
    tomorrow_name = DAYS[tomorrow_weekday]

    query = db.query(Event).filter(
        Event.type == EventType.zajecia,
        Event.day_of_week == tomorrow_name,
        Event.is_cancelled == False,  # noqa: E712
    )
    if schedule_id:
        query = query.filter(Event.schedule_id == schedule_id)

    return tomorrow_name, query.order_by(Event.time_start).all()


def _format_message(day_name: str, events) -> str:
    if not events:
        return f"Jutro ({day_name}) nie masz żadnych zajęć!"
    lines = [f"Plan na jutro ({day_name}):\n"]
    for e in events:
        lines.append(f"• {e.time_start}-{e.time_end} {e.title} | {e.location} | {e.lecturer}")
    return "\n".join(lines)


def send_daily_notification():
    """Globalny email - plan ogólny (bez filtra per user). Zostaje dla kompatybilności."""
    from app.services.notifier import send_notification

    db = SessionLocal()
    try:
        day_name, events = _tomorrow_events(db)
        message = _format_message(day_name, events)
        send_notification(message)
    finally:
        db.close()


def send_telegram_notifications():
    """Wysyła każdemu użytkownikowi powiadomienie dla jego planu."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return

    from telegram import Bot

    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.telegram_chat_id.isnot(None),
            User.schedule_id.isnot(None),
        ).all()

        if not users:
            return

        bot = Bot(token=token)

        async def _send_all():
            for user in users:
                day_name, events = _tomorrow_events(db, user.schedule_id)
                msg = _format_message(day_name, events)
                try:
                    await bot.send_message(chat_id=user.telegram_chat_id, text=msg)
                except Exception as e:
                    print(f"Błąd Telegram do {user.telegram_chat_id}: {e}")

        asyncio.run(_send_all())
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        send_daily_notification,
        CronTrigger(hour=20, minute=0),
        id="daily_email",
        replace_existing=True,
    )
    scheduler.add_job(
        send_telegram_notifications,
        CronTrigger(hour=20, minute=0),
        id="daily_telegram",
        replace_existing=True,
    )
    scheduler.start()
