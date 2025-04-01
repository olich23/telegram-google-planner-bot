# bot.py
import logging
import pickle
import os
import io
import base64
from datetime import datetime, timedelta, timezone
import pytz
import dateparser
import re
import calendar
import httpx

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv
from telegram.error import TelegramError

from natasha import (
    NewsEmbedding,
    Segmenter,
    MorphVocab,
    DatesExtractor
)

emb = NewsEmbedding()
morph_vocab = MorphVocab()
segmenter = Segmenter()

dates_extractor = DatesExtractor(morph_vocab)


load_dotenv()
logging.basicConfig(level=logging.INFO)

ASK_TASK_TEXT = 0
ASK_TASK_DATE = 1
ASK_TASK_DURATION = 2
ASK_DONE_INDEX = 3
ASK_EVENT_TITLE = 4
ASK_EVENT_DATE = 5
ASK_EVENT_START = 6
ASK_EVENT_END = 7

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]

MINSK_TZ = pytz.timezone("Europe/Minsk")
RUSSIAN_WEEKDAYS = {
    'Monday': 'Понедельник',
    'Tuesday': 'Вторник',
    'Wednesday': 'Среда',
    'Thursday': 'Четверг',
    'Friday': 'Пятница',
    'Saturday': 'Суббота',
    'Sunday': 'Воскресенье',
}

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "openrouter/ggml-openchat-3.5-0106"

def format_russian_date(date_obj):
    weekday = RUSSIAN_WEEKDAYS[date_obj.strftime("%A")]
    return f"{weekday} ({date_obj.strftime('%d.%m')})"

def get_credentials():
    creds = None
    encoded_token = os.getenv("GOOGLE_TOKEN")
    if encoded_token:
        try:
            token_data = base64.b64decode(encoded_token)
            creds = pickle.load(io.BytesIO(token_data))
        except Exception as e:
            logging.error(f"Ошибка загрузки токена: {e}")
    if not creds:
        flow = InstalledAppFlow.from_client_config(
            eval(os.getenv("GOOGLE_CREDENTIALS")), SCOPES
        )
        creds = flow.run_local_server(port=0)
    return creds

def extract_datetime_from_text(text: str):
    print("🔥 extract_datetime_from_text ЗАПУСТИЛСЯ")
    print(f"[DEBUG] 🧠 Анализирую текст: {text}")
    now = datetime.now(MINSK_TZ)

    matches = list(dates_extractor(text))
    print(f"[DEBUG] Нашёл {len(matches)} совпадений через Natasha")
    if matches:
        match = matches[0]
        date_fact = match.fact
        print(f"[DEBUG] Natasha распознала: {date_fact}")
        if date_fact:
            year = date_fact.year or now.year
            month = date_fact.month or now.month
            day = date_fact.day or now.day
            hour = date_fact.hour or 9
            minute = date_fact.minute or 0
            return datetime(year, month, day, hour, minute, tzinfo=MINSK_TZ)

    print("[DEBUG] Natasha не справилась, пробуем dateparser...")

    text_lower = text.lower()
    candidates = re.findall(r"(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье|завтра|сегодня|послезавтра|\d{1,2}[:.]\d{2}|\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)", text_lower)
    print(f"[DEBUG] Найдено кандидат(ов) на дату: {candidates}")

    # Комбинируем пары
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            combined = candidates[i] + " " + candidates[j]
            dp_result = dateparser.parse(combined, languages=['ru'], settings={
                "TIMEZONE": "Europe/Minsk",
                "TO_TIMEZONE": "Europe/Minsk",
                "RETURN_AS_TIMEZONE_AWARE": True
            })
            if dp_result:
                print(f"[DEBUG] dateparser распознал из '{combined}': {dp_result}")
                return dp_result

    # Обработка словесных дней недели отдельно
    weekdays = {
        "понедельник": 0,
        "вторник": 1,
        "среда": 2,
        "четверг": 3,
        "пятница": 4,
        "суббота": 5,
        "воскресенье": 6,
    }
    for word in candidates:
        if word in weekdays:
            target_weekday = weekdays[word]
            today = now.weekday()
            days_ahead = (target_weekday - today + 7) % 7
            days_ahead = days_ahead or 7
            future_date = now + timedelta(days=days_ahead)
            future_date = future_date.replace(hour=9, minute=0, second=0, microsecond=0)
            print(f"[DEBUG] День недели '{word}' интерпретирован как: {future_date}")
            return future_date

        if word in ["завтра", "сегодня", "послезавтра"]:
            dp_result = dateparser.parse(word, languages=['ru'], settings={
                "TIMEZONE": "Europe/Minsk",
                "TO_TIMEZONE": "Europe/Minsk",
                "RETURN_AS_TIMEZONE_AWARE": True
            })
            if dp_result:
                print(f"[DEBUG] dateparser распознал '{word}' как: {dp_result}")
                return dp_result

    print("[DEBUG] Ни Natasha, ни dateparser не распознали дату 😢")
    return None


def parse_duration(text):
    text = text.lower().strip()

    # Стандартизированные фразы
    if text in ["час", "один час", "1 час"]:
        return "1 час"
    if text in ["полчаса", "пол часа"]:
        return "30 минут"

    # Формат с дробью: 1.5 часа / 1,5 часа
    match = re.match(r"(\d+)[.,](\d+)\s*час", text)
    if match:
        hours = int(match.group(1))
        decimal = int(match.group(2))
        minutes = round(float(f"0.{decimal}") * 60)
        return f"{hours} час {minutes} минут"

    # Формат: 2 часа 30 минут
    match = re.match(r"(?:(\d+)\s*час[аов]?)?\s*(?:(\d+)\s*минут[ы]?)?", text)
    if match:
        hours = match.group(1)
        minutes = match.group(2)
        result = []
        if hours:
            result.append(f"{hours} час")
        if minutes:
            result.append(f"{minutes} минут")
        return " ".join(result).strip()

    # Только часы
    match = re.match(r"(\d+)\s*час", text)
    if match:
        return f"{match.group(1)} час"

    # Только минуты
    match = re.match(r"(\d+)\s*мин", text)
    if match:
        return f"{match.group(1)} минут"

    return text  # на всякий случай, если ничего не подошло


def weekday_to_date(word):
    weekdays = {
        "понедельник": 0,
        "вторник": 1,
        "среда": 2,
        "четверг": 3,
        "пятница": 4,
        "суббота": 5,
        "воскресенье": 6
    }
    today = datetime.now(MINSK_TZ).date()
    target_weekday = weekdays.get(word.lower())
    if target_weekday is None:
        return None

    days_ahead = (target_weekday - today.weekday() + 7) % 7
    days_ahead = days_ahead or 7  # Если сегодня пятница и пишем "пятница", то следующая

    return datetime.combine(today + timedelta(days=days_ahead), datetime.min.time()).replace(tzinfo=MINSK_TZ)

def parse_duration(text):
    text = text.lower().strip()

    # Словесные варианты
    if text in ["час", "1 час", "один час"]:
        return "1 час"
    if text in ["полчаса", "пол часа"]:
        return "30 минут"

    # Проверка на "1.5 часа", "1,5 часа"
    match = re.match(r"(\d+)[.,](\d+)\s*час", text)
    if match:
        hours = int(match.group(1))
        minutes = int(round(float("0." + match.group(2)) * 60))
        return f"{hours} час {minutes} минут"

    # Проверка на количество часов
    match = re.match(r"(\d+)\s*час", text)
    if match:
        return f"{match.group(1)} час"

    # Проверка на количество минут
    match = re.match(r"(\d+)\s*мин", text)
    if match:
        return f"{match.group(1)} минут"

    # Попробуем найти оба
    match = re.match(r"(?:(\d+)\s*час[аов]?)?\s*(?:(\d+)\s*минут[ы]?)?", text)
    if match:
        h = match.group(1)
        m = match.group(2)
        parts = []
        if h:
            parts.append(f"{h} час")
        if m:
            parts.append(f"{m} минут")
        return " ".join(parts)

    return text  # fallback — просто сохранить как есть



async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    service = build("tasks", "v1", credentials=creds)
    results = service.tasks().list(tasklist='@default', showCompleted=False).execute()
    items = results.get('items', [])

    if not items:
        await update.message.reply_text("🎉 У тебя нет активных задач.")
        return

    grouped = {}
    for task in items:
        due = task.get('due')
        try:
            if due:
                due_dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                    tzinfo=timezone.utc
                ).astimezone(MINSK_TZ)
                key = due_dt.date()
            else:
                key = "Без даты"
        except Exception:
            key = "Без даты"

        grouped.setdefault(key, []).append(task)

    lines = ["📝 Твои задачи:"]
    for key in sorted(grouped.keys()):
        if key == "Без даты":
            lines.append("📅 Без даты:")
        else:
            weekday = RUSSIAN_WEEKDAYS[datetime.combine(key, datetime.min.time()).strftime("%A")]
            lines.append(f"\n📅 {weekday} ({key.strftime('%d.%m')}):")

        for task in grouped[key]:
            line = f"• {task['title']}"
            if task.get("notes"):
                line += f" — {task['notes']}"
            lines.append(line)

    await update.message.reply_text("\n".join(lines))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = """👋 Привет! Я бот-планировщик. Вот что я умею:

📝 /addtask — добавить задачу с датой и временем
📋 /listtasks — показать список всех активных задач
✅ /done — выбрать и отметить задачу как выполненную
📅 /addevent — запланировать встречу в Google Календарь
📆 /today — показать задачи и встречи на сегодня
⏰ /overdue — показать просроченные задачи
❌ /cancel — отменить текущую операцию
"""
    keyboard = [["📝 Добавить задачу", "📋 Показать задачи"],
                ["✅ Завершить задачу", "📅 Добавить встречу"],
                ["📆 Сегодня", "⏰ Просроченные"],
                ["❌ Отменить"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(menu + "\n\nВыберите действие с помощью кнопок ниже:", reply_markup=reply_markup)

async def addtask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Введи текст задачи:")
    return ASK_TASK_TEXT

async def received_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['task_title'] = update.message.text
    await update.message.reply_text("📅 Укажи дату (в формате ДД.ММ.ГГГГ):")
    return ASK_TASK_DATE

async def received_task_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date = datetime.strptime(update.message.text, "%d.%m.%Y")
        context.user_data['task_due'] = date.isoformat() + "Z"
        await update.message.reply_text("⏱ Сколько времени планируешь на выполнение? (например: 1 час, 30 минут)")
        return ASK_TASK_DURATION
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Попробуй снова: ДД.ММ.ГГГГ")
        return ASK_TASK_DATE

async def received_task_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text
    parsed_duration = parse_duration(raw_text)

    creds = get_credentials()
    service = build("tasks", "v1", credentials=creds)
    task = {
        "title": context.user_data['task_title'],
        "due": context.user_data['task_due'],
        "notes": f"Планируемое время: {parsed_duration}"
    }
    service.tasks().insert(tasklist='@default', body=task).execute()
    await update.message.reply_text(f"✅ Задача добавлена!\n🕒 {parsed_duration}")
    return ConversationHandler.END



async def done_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    service = build("tasks", "v1", credentials=creds)
    result = service.tasks().list(tasklist='@default', showCompleted=False).execute()
    items = result.get('items', [])
    if not items:
        await update.message.reply_text("❌ Нет активных задач для завершения.")
        return ConversationHandler.END
    context.user_data['tasks'] = items
    message = "Выбери номер задачи, которую хочешь завершить:\n"
    for idx, task in enumerate(items, 1):
        message += f"{idx}. {task['title']}\n"
    await update.message.reply_text(message)
    return ASK_DONE_INDEX

async def mark_selected_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        index = int(update.message.text) - 1
        items = context.user_data.get('tasks', [])
        if 0 <= index < len(items):
            task = items[index]
            task['status'] = 'completed'
            creds = get_credentials()
            service = build("tasks", "v1", credentials=creds)
            service.tasks().update(tasklist='@default', task=task['id'], body=task).execute()
            await update.message.reply_text(f"✅ Задача завершена: {task['title']}")
        else:
            await update.message.reply_text("❌ Неверный номер. Попробуй снова.")
            return ASK_DONE_INDEX
    except ValueError:
        await update.message.reply_text("❌ Введи номер задачи.")
        return ASK_DONE_INDEX
    return ConversationHandler.END

async def today_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    now = datetime.now(MINSK_TZ)
    today_start = datetime(now.year, now.month, now.day, tzinfo=MINSK_TZ)
    today_end = today_start + timedelta(days=1)

    # Формат заголовка
    formatted_today = format_russian_date(today_start)
    lines = [f"📆 Сегодня: {formatted_today}"]

    # Получаем задачи
    task_service = build("tasks", "v1", credentials=creds)
    result = task_service.tasks().list(tasklist='@default', showCompleted=False).execute()
    tasks = result.get('items', [])

    today_tasks = []
    for task in tasks:
        due = task.get("due")
        if due:
            try:
                due_dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).astimezone(MINSK_TZ)
                if today_start <= due_dt < today_end:
                    line = f"• {task['title']}"
                    if task.get("notes"):
                        line += f" — {task['notes']}"
                    today_tasks.append(line)
            except Exception as e:
                logging.warning(f"Ошибка в обработке задачи: {e}")

    lines.append("\n📝 Задачи:")
    lines.extend(today_tasks or ["Нет задач на сегодня."])

    # Получаем встречи
    calendar_service = build("calendar", "v3", credentials=creds)
    events_result = calendar_service.events().list(
        calendarId='primary',
        timeMin=today_start.isoformat(),
        timeMax=today_end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    lines.append("\n🕒 Встречи:")
    if events:
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'Без названия')
            if 'T' in start:
                start_time = datetime.fromisoformat(start).astimezone(MINSK_TZ)
                lines.append(f"• {summary} в {start_time.strftime('%H:%M')}")
            else:
                lines.append(f"• {summary}")
    else:
        lines.append("Нет встреч на сегодня.")

    await update.message.reply_text("\n".join(lines))



async def overdue_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    now = datetime.now(MINSK_TZ)
    service = build("tasks", "v1", credentials=creds)
    result = service.tasks().list(tasklist='@default', showCompleted=False).execute()
    tasks = result.get('items', [])

    grouped_tasks = {}

    for task in tasks:
        due = task.get("due")
        if due:
            try:
                due_dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).astimezone(MINSK_TZ)
                if due_dt < now:
                    key = due_dt.date()
                    if key not in grouped_tasks:
                        grouped_tasks[key] = []
                    task_line = f"• {task['title']}"
                    if task.get("notes"):
                        task_line += f" — {task['notes']}"
                    grouped_tasks[key].append(task_line)
            except Exception as e:
                logging.warning(f"Ошибка в overdue: {e}")
                continue

    if not grouped_tasks:
        await update.message.reply_text("✅ У тебя нет просроченных задач!")
        return

    lines = ["⏰ Просроченные задачи:"]
    for date in sorted(grouped_tasks.keys()):
        lines.append(f"\n{format_russian_date(datetime.combine(date, datetime.min.time()))}")
        lines.extend(grouped_tasks[date])

    await update.message.reply_text("\n".join(lines))


async def addevent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 Введи название встречи:")
    return ASK_EVENT_TITLE

async def received_event_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text:
        context.user_data['event_title'] = text
        await update.message.reply_text("📅 Укажи дату встречи (ДД.ММ.ГГГГ):")
        return ASK_EVENT_DATE
    else:
        await update.message.reply_text("❌ Название не может быть пустым. Введи ещё раз:")
        return ASK_EVENT_TITLE


async def received_event_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        parsed_date = datetime.strptime(text, "%d.%m.%Y")
        context.user_data['event_date'] = parsed_date.strftime("%d.%m.%Y")
        await update.message.reply_text("🕕 Укажи время окончания встречи (например: 15:30):")
        return ASK_EVENT_END  # ← вот это важно!
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Попробуй снова: ДД.ММ.ГГГГ")
        return ASK_EVENT_DATE

async def received_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event_start'] = update.message.text
    await update.message.reply_text("🕕 Укажи время окончания (например: 15:30):")
    return ASK_EVENT_END

async def received_event_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = context.user_data['event_title']
        date = context.user_data['event_date']
        start_time = context.user_data['event_start']
        end_time = update.message.text

        start_dt = datetime.strptime(f"{date} {start_time}", "%d.%m.%Y %H:%M")
        end_dt = datetime.strptime(f"{date} {end_time}", "%d.%m.%Y %H:%M")

        event = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/Minsk'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Europe/Minsk'},
            'description': 'Добавлено через Telegram-бота'
        }

        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        service.events().insert(calendarId='primary', body=event).execute()

        await update.message.reply_text(f"✅ Встреча '{title}' добавлена в календарь!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении события: {e}")
    return ConversationHandler.END

async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lowered = text.lower()
    print(f"[DEBUG] handle_free_text вызван: {text}")

    # 💡 Сначала проверим явное намерение "встреча"
    if any(kw in lowered for kw in ["встреч", "созвон", "звонок", "встрет"]):
        print("[DEBUG] Распознано намерение: встреча")
        context.user_data.clear()
        context.user_data['event_title'] = text
        dt = extract_datetime_from_text(text)
        if dt:
            context.user_data['event_date'] = dt.strftime("%d.%m.%Y")
            context.user_data['event_start'] = dt.strftime("%H:%M")
            await update.message.reply_text("🕕 Укажи время окончания встречи (например: 15:30):")
            return ASK_EVENT_END
        else:
            await update.message.reply_text("📅 Когда назначить встречу? (например: завтра в 14:00):")
            return ASK_EVENT_DATE

    # ✅ Затем проверим задачу
    if any(kw in lowered for kw in ["нужно", "задача", "сделать", "планирую"]):
        print("[DEBUG] Распознано намерение: задача")
        context.user_data.clear()
        context.user_data['task_title'] = text
        dt = extract_datetime_from_text(text)
        if dt:
            context.user_data['task_due'] = dt.isoformat()
            await update.message.reply_text("⏱ Сколько времени планируешь на выполнение? (например: 1 час, 30 минут)")
            return ASK_TASK_DURATION
        else:
            await update.message.reply_text("📅 Укажи дату задачи (например: завтра, 01.04.2025):")
            return ASK_TASK_DATE

    # 🧠 Теперь — если уже в процессе
    if 'task_title' in context.user_data and 'task_due' not in context.user_data:
        print("[DEBUG] Внутри блока ожидания даты для задачи")
        dt = extract_datetime_from_text(text)
        if dt:
            context.user_data['task_due'] = dt.isoformat()
            await update.message.reply_text("⏱ Сколько времени планируешь на выполнение? (например: 1 час, 30 минут)")
            return ASK_TASK_DURATION
        else:
            await update.message.reply_text("❌ Не понял дату. Введи снова (например: завтра, 01.04.2025):")
            return ASK_TASK_DATE

    if 'event_title' in context.user_data and 'event_date' not in context.user_data:
        print("[DEBUG] Внутри блока ожидания даты для встречи")
        dt = extract_datetime_from_text(text)
        if dt:
            context.user_data['event_date'] = dt.strftime("%d.%m.%Y")
            context.user_data['event_start'] = dt.strftime("%H:%M")
            await update.message.reply_text("🕕 Укажи время окончания встречи (например: 15:30):")
            return ASK_EVENT_END
        else:
            await update.message.reply_text("❌ Не понял дату. Введи снова (например: завтра, 01.04.2025):")
            return ASK_EVENT_DATE

    if all(key in context.user_data for key in ['event_title', 'event_date', 'event_start']) and 'event_end' not in context.user_data:
        print("[DEBUG] Ожидаем время окончания встречи")
        context.user_data['event_end'] = text
        return await received_event_end(update, context)

    print("[DEBUG] Не распознано ни встреча, ни задача")
    await update.message.reply_text("🤔 Я пока не понимаю это сообщение. Попробуй использовать команды или кнопки.")
    return ConversationHandler.END

async def ask_openrouter(prompt):
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logging.warning(f"Ошибка при обращении к OpenRouter: {e}")
        return None

async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    print(f"[DEBUG] handle_free_text вызван: {text}")

    # 🧠 Сначала пробуем спросить ИИ
    system_prompt = (
        "Ты помощник планировщика. Пользователь может написать, что хочет сделать."
        "Распознай, нужно ли создать задачу или встречу и выведи результат в формате JSON:"
        "{\"type\": \"task|event\", \"title\": \"...\", \"date\": \"дд.мм.гггг\", \"time\": \"чч:мм\" (или null)}"
        "Если непонятно — верни null."
    )
    user_prompt = f"Сообщение: {text}"
    combined_prompt = f"{system_prompt}\n{user_prompt}"

    result = await ask_openrouter(combined_prompt)
    if result:
        try:
            parsed = eval(result.strip()) if result.strip().startswith("{") else None
            if isinstance(parsed, dict):
                task_type = parsed.get("type")
                title = parsed.get("title")
                date = parsed.get("date")
                time = parsed.get("time")

                if task_type == "task":
                    context.user_data.clear()
                    context.user_data['task_title'] = title
                    if date:
                        try:
                            dt = datetime.strptime(f"{date} {time or '09:00'}", "%d.%m.%Y %H:%M")
                            context.user_data['task_due'] = dt.astimezone(MINSK_TZ).isoformat()
                            await update.message.reply_text("⏱ Сколько времени планируешь на выполнение? (например: 1 час, 30 минут)")
                            return ASK_TASK_DURATION
                        except:
                            pass
                    await update.message.reply_text("📅 Укажи дату задачи (например: завтра, 01.04.2025):")
                    return ASK_TASK_DATE

                elif task_type == "event":
                    context.user_data.clear()
                    context.user_data['event_title'] = title
                    if date:
                        context.user_data['event_date'] = date
                        context.user_data['event_start'] = time or "09:00"
                        await update.message.reply_text("🕕 Укажи время окончания встречи (например: 15:30):")
                        return ASK_EVENT_END
                    await update.message.reply_text("📅 Когда назначить встречу? (например: завтра в 14:00):")
                    return ASK_EVENT_DATE
        except Exception as e:
            print(f"[DEBUG] Ошибка разбора ответа OpenRouter: {e}")

    print("[DEBUG] ИИ не помог, используем fallback-логику")
    await update.message.reply_text("🤔 Я пока не понимаю это сообщение. Попробуй использовать команды или кнопки.")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(msg="Exception while handling update:", exc_info=context.error)


def main():
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addevent", addevent_start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("listtasks", list_tasks))
    app.add_handler(CommandHandler("today", today_tasks))
    app.add_handler(CommandHandler("overdue", overdue_tasks))

    # Кнопки быстрого доступа
    app.add_handler(MessageHandler(filters.Regex(r"^📋 Показать задачи$"), list_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^📆 Сегодня$"), today_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^⏰ Просроченные$"), overdue_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^❌ Отменить$"), cancel))

    app.add_handler(ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text)
        ],
        states={
            ASK_TASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_date)],
            ASK_TASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_duration)],
            ASK_EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_date)],
            ASK_EVENT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_start)],
            ASK_EVENT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_end)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    ))
    
    # ConversationHandler — Добавить задачу (через команду и кнопку)
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("addtask", addtask_start),
            MessageHandler(filters.Regex(r"^📝 Добавить задачу$"), addtask_start)
        ],
        states={
            ASK_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_text)],
            ASK_TASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_date)],
            ASK_TASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_duration)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    ))

    # ConversationHandler — Добавить встречу (через команду и кнопку)
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("addevent", addevent_start),
            MessageHandler(filters.Regex(r"^📅 Добавить встречу$"), addevent_start)
        ],
        states={
            ASK_EVENT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_title)],
            ASK_EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_date)],
            ASK_EVENT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_start)],
            ASK_EVENT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_end)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    ))

    # ConversationHandler — Завершить задачу (через команду и кнопку)
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("done", done_start),
            MessageHandler(filters.Regex(r"^✅ Завершить задачу$"), done_start)
        ],
        states={
            ASK_DONE_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, mark_selected_done)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )) 
    
    
    
    app.add_error_handler(error_handler)


    
    print("🚀 Бот запущен. Жду команды...")
    app.run_polling()



if __name__ == "__main__":
    main()
