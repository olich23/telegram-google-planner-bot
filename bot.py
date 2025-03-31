import logging
import pickle
import os
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Логгирование
logging.basicConfig(level=logging.INFO)

# Состояния для диалога
ASK_TASK_TEXT = 0
ASK_TASK_DATE = 1
ASK_TASK_DURATION = 2
ASK_DONE_INDEX = 3
ASK_EVENT_TITLE = 4
ASK_EVENT_DATE = 5
ASK_EVENT_START = 6
ASK_EVENT_END = 7

# Области доступа Google API
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]

# Авторизация Google

def get_credentials():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return creds

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import ReplyKeyboardMarkup

    menu = """
👋 Привет! Я бот-планировщик. Вот что я умею:

📝 /addtask — добавить задачу с датой и временем
📋 /listtasks — показать список всех активных задач
✅ /done — выбрать и отметить задачу как выполненную
📅 /addevent — запланировать встречу в Google Календарь
📆 /today — показать задачи и встречи на сегодня
❌ /cancel — отменить текущую операцию
    """

    keyboard = [["📝 Добавить задачу", "📋 Показать задачи"], ["✅ Завершить задачу", "📅 Добавить встречу"], ["📆 Сегодня", "❌ Отменить"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(menu + "Выберите действие с помощью кнопок ниже:", reply_markup=reply_markup)

# Старт диалога задачи
async def addtask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Введи текст задачи:")
    return ASK_TASK_TEXT

# Получение текста задачи
async def received_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['task_title'] = update.message.text
    await update.message.reply_text("📅 Укажи дату (в формате ДД.ММ.ГГГГ):")
    return ASK_TASK_DATE

# Получение даты задачи
async def received_task_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text
    try:
        due_date = datetime.strptime(date_text, "%d.%m.%Y").isoformat() + "Z"
        context.user_data['task_due'] = due_date
        await update.message.reply_text("⏱ Сколько времени планируешь на выполнение? (например: 1 час, 30 минут)")
        return ASK_TASK_DURATION
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Попробуй снова: ДД.ММ.ГГГГ")
        return ASK_TASK_DATE

# Получение длительности задачи
async def received_task_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    duration = update.message.text
    creds = get_credentials()
    service = build("tasks", "v1", credentials=creds)

    task = {
        "title": context.user_data['task_title'],
        "due": context.user_data['task_due'],
        "notes": f"Планируемое время: {duration}\nДобавлено через Telegram-бота"
    }

    result = service.tasks().insert(tasklist='@default', body=task).execute()
    await update.message.reply_text(f"✅ Задача добавлена: {result['title']}")
    return ConversationHandler.END

# Старт диалога встречи
async def addevent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 Введи название встречи:")
    return ASK_EVENT_TITLE

async def received_event_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event_title'] = update.message.text
    await update.message.reply_text("📅 Укажи дату встречи (ДД.ММ.ГГГГ):")
    return ASK_EVENT_DATE

async def received_event_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event_date'] = update.message.text
    await update.message.reply_text("🕒 Укажи время начала (например: 14:30):")
    return ASK_EVENT_START

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
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'Europe/Minsk',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'Europe/Minsk',
            },
            'description': 'Добавлено через Telegram-бота'
        }

        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        service.events().insert(calendarId='primary', body=event).execute()

        await update.message.reply_text(f"✅ Встреча '{title}' добавлена в календарь!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении события: {e}")
    return ConversationHandler.END

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

# Команда /listtasks
async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    service = build("tasks", "v1", credentials=creds)

    results = service.tasks().list(tasklist='@default', showCompleted=False).execute()
    items = results.get('items', [])

    if not items:
        await update.message.reply_text("🎉 У тебя нет активных задач.")
        return

    message = "📝 Твои задачи:"
    for idx, task in enumerate(items, start=1):
        title = task['title']
        notes = task.get('notes', '')
        due = task.get('due')
        due_str = f" (на {due[:10]})" if due else ""
        duration = ""
        if "Планируемое время:" in notes:
            for line in notes.splitlines():
                if "Планируемое время:" in line:
                    duration = f" — {line.strip()}"
        message += f"{idx}. {title}{due_str}{duration}"

    context.user_data['tasks'] = items
    await update.message.reply_text(message)

# Старт завершения задачи
async def done_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    service = build("tasks", "v1", credentials=creds)

    results = service.tasks().list(tasklist='@default', showCompleted=False).execute()
    items = results.get('items', [])

    if not items:
        await update.message.reply_text("❌ Нет активных задач для завершения.")
        return ConversationHandler.END

    message = "Выбери номер задачи, которую хочешь завершить:\n"
    for idx, task in enumerate(items, start=1):
        message += f"{idx}. {task['title']}\n"

    context.user_data['tasks'] = items
    await update.message.reply_text(message)
    return ASK_DONE_INDEX

# Завершение выбранной задачи
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
        await update.message.reply_text("❌ Пожалуйста, введи номер задачи.")
        return ASK_DONE_INDEX

    return ConversationHandler.END

# Основной запуск
if __name__ == "__main__":
    TOKEN = "7970819733:AAFkStb9GpNZgpLaHpzSEyE4DG3i_gx2E5o"

    app = ApplicationBuilder().token(TOKEN).build()

    # Диалог по добавлению задачи
    add_task_conv = ConversationHandler(
        entry_points=[CommandHandler("addtask", addtask_start)],
        states={
            ASK_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_text)],
            ASK_TASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_date)],
            ASK_TASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_duration)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Диалог завершения задачи
    done_task_conv = ConversationHandler(
        entry_points=[CommandHandler("done", done_start)],
        states={
            ASK_DONE_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, mark_selected_done)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Диалог добавления встречи
    add_event_conv = ConversationHandler(
        entry_points=[CommandHandler("addevent", addevent_start)],
        states={
            ASK_EVENT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_title)],
            ASK_EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_date)],
            ASK_EVENT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_start)],
            ASK_EVENT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_end)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))

    # Обработка текстовых кнопок как эквивалентов команд
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📝 Добавить задачу$"), addtask_start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📋 Показать задачи$"), list_tasks))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^✅ Завершить задачу$"), done_start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📅 Добавить встречу$"), addevent_start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^❌ Отменить$"), cancel))
    # Команда '📆 Сегодня' подключим, когда сделаем today    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: context.application.create_task(context.application.process_update(update))))
    app.add_handler(add_task_conv)
    app.add_handler(done_task_conv)
    app.add_handler(add_event_conv)
    app.add_handler(CommandHandler("listtasks", list_tasks))

    print("🚀 Бот запущен. Жду команды...")
    app.run_polling()
