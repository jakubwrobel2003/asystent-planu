from fastapi import FastAPI
from app.database import engine, Base
from app.routers import schedule, chat

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Asystent Planu")

app.include_router(schedule.router, prefix="/schedule", tags=["schedule"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])


@app.get("/")
def root():
    return {"status": "działa"}

@app.get("/test-notification")
def test_notification():
    from app.services.scheduler import send_daily_notification
    send_daily_notification()
    return {"status": "wysłano"}