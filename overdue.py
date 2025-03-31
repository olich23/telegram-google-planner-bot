from telegram import Update
from telegram.ext import ContextTypes
from auth import get_credentials
from auth_utils import MINSK_TZ
from googleapiclient.discovery import build
from datetime import datetime, timezone

async def overdue_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    now = datetime.now(MINSK_TZ)
    service = build("tasks", "v1", credentials=creds)
    result = service.tasks().list(tasklist='@default', showCompleted=False).execute()
    tasks = result.get('items', [])
    overdue = []
    for task in tasks:
        due = task.get("due")
        if due:
            try:
                due_dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).astimezone(MINSK_TZ)
                if due_dt < now:
                    overdue.append(f"❗ {task['title']} (на {due_dt.strftime('%d.%m.%Y')})")
            except Exception:
                continue
    if overdue:
        await update.message.reply_text("⏰ Просроченные задачи:\n" + "\n".join(overdue))
    else:
        await update.message.reply_text("✅ У тебя нет просроченных задач!")
