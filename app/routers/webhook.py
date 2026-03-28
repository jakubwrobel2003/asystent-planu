from fastapi import APIRouter, Form
from twilio.rest import Client
import os
from app.database import SessionLocal
from app.services.claude import ask_claude
from app.routers.chat import get_schedule_context

router = APIRouter()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")


@router.post("/webhook")
async def whatsapp_webhook(
    Body: str = Form(...),
    From: str = Form(...)
):
    db = SessionLocal()
    try:
        context = get_schedule_context(db)
        result = ask_claude(Body, context)

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=result["text"],
            from_=TWILIO_WHATSAPP_FROM,
            to=From
        )

        if result["action"]:
            from app.routers.chat import apply_action
            apply_action(result["action"], db)

    finally:
        db.close()

    return {"status": "ok"}