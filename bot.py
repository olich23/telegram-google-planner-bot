# бот с интеграцией OpenRouter (OpenAI API) для обработки свободного ввода
import logging
import pickle
import os
import io
import base64
import json
from datetime import datetime, timedelta, timezone
import pytz

import openai  # просто импортируем openai, без импорта ChatCompletion

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Состояния для ConversationHandler
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

# Остальные функции бота (list_tasks, addtask_start, received_task_text и т.д.) остаются без изменений

# --- Новый раздел: обработка ИИ-команды через OpenRouter ---

# Функция для выполнения команды, полученной от ИИ
async def process_ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE, command_dict):
    command = command_dict.get("command")
    params = command_dict.get("params", {})

    if command == "addtask":
        title = params.get("title")
        date = params.get("date")
        duration = params.get("duration")
        if not title or not date or not duration:
            await update.message.reply_text("❌ Для добавления задачи необходимы: название, дата и продолжительность.")
            return
        try:
            task_date = datetime.strptime(date, "%d.%m.%Y")
            due = task_date.isoformat() + "Z"
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
            return
        creds = get_credentials()
        service = build("tasks", "v1", credentials=creds)
        task = {
            "title": title,
            "due": due,
            "notes": f"Планируемое время: {duration}"
        }
        service.tasks().insert(tasklist='@default', body=task).execute()
        await update.message.reply_text("✅ Задача добавлена через ИИ!")
    elif command == "listtasks":
        from_task = await list_tasks(update, context)
        return from_task
    elif command == "done":
        return await done_start(update, context)
    elif command == "addevent":
        title = params.get("title")
        date = params.get("date")
        start_time = params.get("start")
        end_time = params.get("end")
        if not title or not date or not start_time or not end_time:
            await update.message.reply_text("❌ Для добавления встречи необходимы: название, дата, время начала и время окончания.")
            return
        try:
            start_dt = datetime.strptime(f"{date} {start_time}", "%d.%m.%Y %H:%M")
            end_dt = datetime.strptime(f"{date} {end_time}", "%d.%m.%Y %H:%M")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты или времени.")
            return
        event = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/Minsk'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Europe/Minsk'},
            'description': 'Добавлено через Telegram-бота (ИИ)'
        }
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        service.events().insert(calendarId='primary', body=event).execute()
        await update.message.reply_text(f"✅ Встреча '{title}' добавлена в календарь через ИИ!")
    elif command == "today":
        return await today_tasks(update, context)
    elif command == "overdue":
        return await overdue_tasks(update, context)
    else:
        await update.message.reply_text("❌ Команда не распознана.")

# Обработчик команды /ai с вызовом OpenRouter через openai.ChatCompletion.create
async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.replace("/ai", "").strip()
    
    # Настраиваем параметры OpenRouter
    openai.api_key = "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"
    openai.api_base = "https://openrouter.ai/api/v1"
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты выступаешь в роли маршрутизатора команд для Telegram-бота-планировщика. "
                        "На вход получаешь запрос пользователя в свободной форме. "
                        "Выведи JSON-объект с полем 'command', значение которого может быть одним из: "
                        "'addtask', 'listtasks', 'done', 'addevent', 'today', 'overdue'. "
                        "Если команда требует дополнительных параметров, передай их в поле 'params'. "
                        "Если команда не распознана, выведи 'unknown'. "
                        "Пример: {\"command\": \"addtask\", \"params\": {\"title\": \"Купить хлеб\", \"date\": \"01.01.2025\", \"duration\": \"30 минут\"}}"
                    )
                },
                {"role": "user", "content": user_input}
            ],
            temperature=0
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обращения к OpenRouter: {e}")
        return

    try:
        ai_message = response["choices"][0]["message"]["content"]
        command_dict = json.loads(ai_message)
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось обработать ответ ИИ: {e}")
        return

    await process_ai_command(update, context, command_dict)

def main():
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addevent", addevent_start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("listtasks", list_tasks))
    app.add_handler(CommandHandler("today", today_tasks))
    app.add_handler(CommandHandler("overdue", overdue_tasks))
    # Обработчик для свободного ввода через ИИ
    app.add_handler(CommandHandler("ai", ai_handler))

    # Пример кнопок быстрого доступа
    app.add_handler(MessageHandler(filters.Regex(r"^📋 Показать задачи$"), list_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^📆 Сегодня$"), today_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^⏰ Просроченные$"), overdue_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^❌ Отменить$"), cancel))

    # Регистрируем ConversationHandler-ы для задач и встреч
    # (фрагменты кода для ConversationHandler-ов не изменялись)

    print("🚀 Бот запущен. Жду команды...")
    app.run_polling()

if __name__ == "__main__":
    main()
