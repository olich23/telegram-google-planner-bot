# bot.py
import logging
import pickle
import os
import io
import base64
from datetime import datetime, timedelta, timezone
import pytz

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Импорт нового клиента для Inference от Hugging Face
from huggingface_hub import InferenceClient

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
🤖 /ai — общаться с ИИ (через Hugging Face Inference API)
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
    duration = update.message.text
    creds = get_credentials()
    service = build("tasks", "v1", credentials=creds)
    task = {
        "title": context.user_data['task_title'],
        "due": context.user_data['task_due'],
        "notes": f"Планируемое время: {duration}"
    }
    service.tasks().insert(tasklist='@default', body=task).execute()
    await update.message.reply_text("✅ Задача добавлена!")
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

    formatted_today = format_russian_date(today_start)
    lines = [f"📆 Сегодня: {formatted_today}"]

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
        await update.message.reply_text("🕒 Укажи время начала (например: 14:30):")
        return ASK_EVENT_START
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

# --- Интеграция Hugging Face Inference API с новым InferenceClient ---
# Инициализируем клиента для модели distilgpt2
inference_client = InferenceClient(model="distilgpt2")

def generate_ai_response(prompt, max_length=100):
    # Передаем параметры генерации через словарь
    response = inference_client(inputs=prompt, parameters={"max_new_tokens": max_length})
    # Если ответ приходит в виде списка, берем первый элемент
    if isinstance(response, list) and len(response) > 0:
        generated_text = response[0].get("generated_text", "")
    elif isinstance(response, dict):
        generated_text = response.get("generated_text", "")
    else:
        generated_text = ""
    return generated_text

async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    prompt = text[3:].strip() if text.startswith("/ai") else text.strip()
    if not prompt:
        await update.message.reply_text("Введите сообщение после команды /ai для общения с ИИ.")
        return
    response = generate_ai_response(prompt)
    await update.message.reply_text(response)

def main():
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addevent", addevent_start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("listtasks", list_tasks))
    app.add_handler(CommandHandler("today", today_tasks))
    app.add_handler(CommandHandler("overdue", overdue_tasks))
    # Команда для общения с ИИ
    app.add_handler(CommandHandler("ai", ai_chat))

    # Кнопки быстрого доступа
    app.add_handler(MessageHandler(filters.Regex(r"^📋 Показать задачи$"), list_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^📆 Сегодня$"), today_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^⏰ Просроченные$"), overdue_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^❌ Отменить$"), cancel))

    # ConversationHandler — Добавить задачу
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

    # ConversationHandler — Добавить встречу
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

    # ConversationHandler — Завершить задачу
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

    print("🚀 Бот запущен. Жду команды...")
    app.run_polling()

if __name__ == "__main__":
    main()
