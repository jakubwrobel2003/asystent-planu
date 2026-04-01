import os
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from app.database import SessionLocal
from app.services.claude import ask_claude
from app.routers.chat import get_schedule_context, apply_action

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    chat_id = update.message.chat_id

    db = SessionLocal()
    try:
        schedule_context = get_schedule_context(db)
        result = ask_claude(message, schedule_context)

        if result["action"]:
            apply_action(result["action"], db)

        await update.message.reply_text(result["text"])
    finally:
        db.close()


def run_bot():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()