import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """Jesteś asystentem studenta który zarządza planem zajęć.

Masz dostęp do bazy zajęć. Gdy użytkownik zgłasza zmianę w planie, 
wyciągnij z wiadomości strukturę JSON z polami:
- action: "update", "cancel", "add", "query"
- title: nazwa przedmiotu
- day_of_week: dzień tygodnia (jeśli dotyczy)
- time_start: nowa godzina rozpoczęcia (jeśli dotyczy)
- time_end: nowa godzina zakończenia (jeśli dotyczy)
- location: sala (jeśli dotyczy)
- notes: dodatkowe info

Jeśli użytkownik tylko pyta o plan — action to "query".
Odpowiadaj zawsze po polsku.
Gdy zwracasz JSON, umieść go między znacznikami <json> i </json>.
Poza JSON-em odpowiadaj normalnie, potwierdzając co zrobiłeś."""


def ask_claude(message: str, schedule_context: str = "") -> dict:
    full_message = message
    if schedule_context:
        full_message = f"Aktualny plan zajęć:\n{schedule_context}\n\nWiadomość użytkownika: {message}"

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": full_message}]
    )

    text = response.content[0].text

    result = {"text": text, "action": None}

    if "<json>" in text and "</json>" in text:
        json_str = text.split("<json>")[1].split("</json>")[0].strip()
        clean_text = text.split("<json>")[0].strip()
        after = text.split("</json>")[-1].strip()
        result["text"] = (clean_text + "\n" + after).strip()
        import json
        try:
            result["action"] = json.loads(json_str)
        except json.JSONDecodeError:
            pass

    if "<json>" in text and "</json>" in text:
        json_str = text.split("<json>")[1].split("</json>")[0].strip()
        import json
        try:
            result["action"] = json.loads(json_str)
        except json.JSONDecodeError:
            pass

    return result