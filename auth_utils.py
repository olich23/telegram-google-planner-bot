import logging
from datetime import datetime, timedelta, timezone
import pytz
from telegram import Update
from telegram.ext import ContextTypes
from googleapiclient.discovery import build
from auth_utils import get_credentials

MINSK_TZ = pytz.timezone("Europe/Minsk")

async def today_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    creds = get_credentials()
    now = datetime.now(MINSK_TZ)
    today_str = now.date()

    service = build("tasks", "v1", credentials=creds)
    result = service.tasks().list(tasklist='@default', showCompleted=False).execute()
    tasks = result.get('items', [])

    today_tasks = []
    for task in tasks:
        due = task.get("due")
        if due:
            try:
                due_dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).astimezone(MINSK_TZ)
                if due_dt.date() == today_str:
                    today_tasks.append(f"✅ {task['title']} (на {due_dt.strftime('%d.%m.%Y')})")
            except Exception as e:
                logging.warning(f"Ошибка в today_tasks: {e}")

    calendar_service = build("calendar", "v3", credentials=creds)
    events_result = calendar_service.events().list(
        calendarId='primary',
        timeMin=now.isoformat(),
        timeMax=(now + timedelta(days=1)).isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    lines = ["📆 Задачи и встречи на сегодня:"]
    lines.extend(today_tasks or ["Задач нет"])

    if events:
        lines.append("\n🕒 Встречи:")
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'Без названия')
            if 'T' in start:
                lines.append(f"• {summary} в {start[11:16]}")
            else:
                lines.append(f"• {summary}")
    else:
        lines.append("Встреч нет")

    await update.message.reply_text("\n".join(lines))
