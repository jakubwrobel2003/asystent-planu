from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.database import SessionLocal
from app.models import Event
from datetime import datetime

scheduler = BackgroundScheduler()


def get_tomorrows_classes():
    db = SessionLocal()
    try:
        tomorrow_weekday = (datetime.now().weekday() + 1) % 7
        days = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
        tomorrow_name = days[tomorrow_weekday]

        events = db.query(Event).filter(
            Event.type == "zajecia",
            Event.day_of_week == tomorrow_name,
            Event.is_cancelled == False
        ).order_by(Event.time_start).all()

        return tomorrow_name, events
    finally:
        db.close()


def send_daily_notification():
    from app.services.notifier import send_notification
    day_name, events = get_tomorrows_classes()

    if not events:
        message = f"Jutro ({day_name}) nie masz żadnych zajęć!"
    else:
        lines = [f"Plan na jutro ({day_name}):\n"]
        for e in events:
            lines.append(f"• {e.time_start}-{e.time_end} {e.title} | {e.location} | {e.lecturer}")
        message = "\n".join(lines)

    send_notification(message)


def start_scheduler():
    scheduler.add_job(
        send_daily_notification,
        CronTrigger(hour=20, minute=0),
        id="daily_notification",
        replace_existing=True
    )
    scheduler.start()