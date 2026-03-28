import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_WHATSAPP_TO = os.getenv("TWILIO_WHATSAPP_TO")


def send_email(message: str):
    if not SENDGRID_API_KEY:
        print("Brak SENDGRID_API_KEY")
        return
    mail = Mail(
        from_email=EMAIL_FROM,
        to_emails=EMAIL_TO,
        subject="Plan zajęć na jutro",
        plain_text_content=message
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        sg.send(mail)
        print("Email wysłany!")
    except Exception as e:
        print(f"Błąd emaila: {e}")


def send_whatsapp(message: str):
    if not TWILIO_ACCOUNT_SID:
        print("Brak TWILIO_ACCOUNT_SID")
        return
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_FROM,
            to=TWILIO_WHATSAPP_TO
        )
        print("WhatsApp wysłany!")
    except Exception as e:
        print(f"Błąd WhatsApp: {e}")


def send_notification(message: str):
    send_email(message)
    send_whatsapp(message)
