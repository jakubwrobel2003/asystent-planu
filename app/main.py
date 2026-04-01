from fastapi import FastAPI, Request
from app.database import engine, Base
from app.routers import schedule, chat
from app.routers.webhook import router as webhook_router
from app.services.scheduler import start_scheduler
import subprocess
subprocess.run(["alembic", "upgrade", "head"], check=True)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Asystent Planu")


from app.routers.admin import router as admin_router
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(schedule.router, prefix="/schedule", tags=["schedule"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(webhook_router, tags=["webhook"])

start_scheduler()

telegram_app = None

@app.on_event("startup")
async def startup():
    global telegram_app
    from app.services.telegram_bot import create_app
    import os
    telegram_app = create_app()
    await telegram_app.initialize()
    railway_url = os.getenv("RAILWAY_URL")
    if railway_url:
        await telegram_app.bot.set_webhook(f"{railway_url}/telegram")
    await telegram_app.start()


@app.on_event("shutdown")
async def shutdown():
    if telegram_app:
        await telegram_app.stop()


@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    from telegram import Update
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


@app.get("/")
def root():
    return {"status": "działa"}


@app.get("/test-notification")
def test_notification():
    from app.services.scheduler import send_daily_notification
    send_daily_notification()
    return {"status": "wysłano"}