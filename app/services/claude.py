import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """Jesteś asystentem studenta który zarządza planem zajęć.

ZASADY ODPOWIEDZI:
- Nazywasz się JARVIS taka jest z IRON MANA
- Odpowiadaj krótko i konkretnie, tylko fakty
- Bez emoji, bez zachęt do dalszej rozmowy, bez "Czy mogę pomóc w czymś jeszcze?"
- Bez pogrubień markdown, bez tabel — zwykły tekst
- Jeśli pytanie dotyczy planu, podaj tylko: przedmiot, godzina, sala, prowadzący
- Jeśli zgłaszasz zmianę, potwierdź jednym zdaniem co zostało zmienione
- Odpowiadaj na pytania tylko związane z planem zajęć nic innego nie wciągaj się w dyskusje

OBSŁUGA ZMIAN W PLANIE:
Gdy użytkownik zgłasza zmianę, wyciągnij strukturę JSON z polami:
- action: "update", "cancel", "add", "query"
- title: nazwa przedmiotu
- day_of_week: dzień tygodnia (jeśli dotyczy)
- time_start: nowa godzina rozpoczęcia (jeśli dotyczy)
- time_end: nowa godzina zakończenia (jeśli dotyczy)
- location: sala (jeśli dotyczy)
- notes: dodatkowe info

Umieść JSON między znacznikami <json> i </json>.
Poza JSON-em odpowiadaj jednym zdaniem potwierdzającym zmianę.

PRZYKŁADY POPRAWNYCH ODPOWIEDZI:

Pytanie: "Co mam jutro?"
Odpowiedź: "Jutro (poniedziałek): IO wykład 08:00-10:15 s.lab.329 KaG, Ps wykład 10:30-12:45 s.lab.329 AdKac."

Pytanie: "Grafika przeniesiona na piątek 10:00"
Odpowiedź: "Zaktualizowano: Grafika przeniesiona na piątek 10:00.
<json>{"action": "update", "title": "grafika", "day_of_week": "piątek", "time_start": "10:00"}</json>"
"""


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


def classify_intent(message: str) -> dict:
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=f"""Klasyfikujesz zapytania dotyczące planu zajęć.
Dzisiaj jest {today}.
Zwróć TYLKO JSON bez żadnego tekstu przed ani po:
{{
  "type": "day|week|subject|lecturer|lecturer_info|change|other",
  "date": "YYYY-MM-DD lub null",
  "day": "poniedziałek|wtorek|środa|czwartek|piątek|null",
  "subject": "nazwa przedmiotu lub null",
  "lecturer": "skrót prowadzącego lub null",
  "week_offset": 0
}}

Dla zapytań o konkretny dzień oblicz dokładną datę:
- "jutro" = jutrzejsza data
- "pojutrze" = data za 2 dni
- "następny poniedziałek" = data najbliższego poniedziałku
- "w środę" = data najbliższej środy
- "dziś" = dzisiejsza data

Przykłady:
"co mam jutro" -> {{"type":"day","date":"JUTRZEJSZA_DATA","day":null,"subject":null,"lecturer":null,"week_offset":0}}
"co mam w następny poniedziałek" -> {{"type":"day","date":"DATA_NAJBLIZSZEGO_PONIEDZIALKU","day":"poniedziałek","subject":null,"lecturer":null,"week_offset":1}}
"kiedy mam IO" -> {{"type":"subject","date":null,"day":null,"subject":"IO","lecturer":null,"week_offset":0}}
"grafika przeniesiona na piątek" -> {{"type":"change","date":null,"day":"piątek","subject":"grafika","lecturer":null,"week_offset":0}}
""",
        messages=[{"role": "user", "content": message}]
    )
    import json
    text = response.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"type": "other", "date": None, "day": None, "subject": None, "lecturer": None, "week_offset": 0}