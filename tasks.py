from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from auth import get_credentials
from googleapiclient.discovery import build
from auth_utils import MINSK_TZ
from datetime import datetime

ASK_TASK_TEXT = 0
ASK_TASK_DATE = 1
ASK_TASK_DURATION = 2
ASK_DONE_INDEX = 3

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    service = build("tasks", "v1", credentials=creds)
    results = service.tasks().list(tasklist='@default', showCompleted=False).execute()
    items = results.get('items', [])
    if not items:
        await update.message.reply_text("🎉 У тебя нет активных задач.")
        return
    message = "📝 Твои задачи:\n"
    for idx, task in enumerate(items, start=1):
        title = task['title']
        notes = task.get('notes', '')
        due = task.get('due')
        due_str = f" (на {due[:10]})" if due else ""
        message += f"{idx}. {title}{due_str}"
        if notes:
            message += f" — {notes}"
        message += "\n"
    context.user_data['tasks'] = items
    await update.message.reply_text(message)

async def addtask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
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
