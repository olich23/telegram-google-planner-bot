from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from googleapiclient.discovery import build
from utils import get_credentials, MINSK_TZ
from datetime import datetime

ASK_EVENT_TITLE, ASK_EVENT_DATE, ASK_EVENT_START, ASK_EVENT_END = range(4)

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
