import os
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from app.database import SessionLocal
from app.services.claude import ask_claude
from app.routers.chat import get_schedule_context, apply_action

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    db = SessionLocal()
    try:
        schedule_context = get_schedule_context(db)
        result = ask_claude(message, schedule_context)
        if result["action"]:
            apply_action(result["action"], db)
        await update.message.reply_text(result["text"])
    finally:
        db.close()


def create_app():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application