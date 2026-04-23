import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import schedule, chat
from app.routers.admin import router as admin_router
from app.services.scheduler import start_scheduler

Base.metadata.create_all(bind=engine)

telegram_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    start_scheduler()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        try:
            from app.services.telegram_bot import create_app as create_tg_app
            telegram_app = create_tg_app()
            await telegram_app.initialize()
            railway_url = os.getenv("RAILWAY_URL")
            if railway_url:
                await telegram_app.bot.set_webhook(f"{railway_url}/telegram")
            await telegram_app.start()
        except Exception as e:
            print(f"Telegram init error: {e}")
            telegram_app = None
    else:
        print("TELEGRAM_BOT_TOKEN nieustawiony — bot Telegram wyłączony")

    yield

    if telegram_app:
        try:
            await telegram_app.stop()
            await telegram_app.shutdown()
        except Exception as e:
            print(f"Telegram shutdown error: {e}")


app = FastAPI(title="Asystent Planu", lifespan=lifespan)

# CORS — dev, otwarte
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schedule.router, prefix="/schedule", tags=["schedule"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])


@app.post("/telegram")
async def telegram_webhook(request: Request):
    if not telegram_app:
        return {"ok": False, "error": "Telegram disabled"}
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
