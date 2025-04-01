import logging
import pickle
import os
import io
import base64
import json
from datetime import datetime, timedelta, timezone
import pytz
import re

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния разговоров
ASK_TASK_TEXT, ASK_TASK_DATE, ASK_TASK_DURATION = range(3)
ASK_DONE_INDEX = 0
ASK_EVENT_TITLE, ASK_EVENT_DATE, ASK_EVENT_START, ASK_EVENT_END = range(4)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]

MINSK_TZ = pytz.timezone("Europe/Minsk")

def get_credentials():
    creds = None
    encoded_token = os.getenv("GOOGLE_TOKEN")
    
    # 1. Пробуем загрузить сохраненные credentials
    if encoded_token:
        try:
            token_data = base64.b64decode(encoded_token)
            creds = pickle.load(io.BytesIO(token_data))
            if creds and creds.valid:
                return creds
        except Exception as e:
            logger.error(f"Ошибка загрузки токена: {e}")

    # 2. Получаем новые credentials
    try:
        encoded_creds = os.getenv("GOOGLE_CREDENTIALS")
        if not encoded_creds:
            raise ValueError("GOOGLE_CREDENTIALS не установлена")
        
        # Декодируем и загружаем JSON
        decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')
        credentials_info = json.loads(decoded_creds)
        
        flow = InstalledAppFlow.from_client_config(credentials_info, SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Сохраняем новые credentials в base64
        token_bytes = pickle.dumps(creds)
        new_encoded_token = base64.b64encode(token_bytes).decode('utf-8')
        logger.info(f"Новый токен сгенерирован. Добавьте в GOOGLE_TOKEN: {new_encoded_token}")
        
        return creds
    except Exception as e:
        logger.error(f"Ошибка получения credentials: {e}")
        raise

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = """
👋 Привет! Я бот-планировщик. Вот что я умею:

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
    context.user_data.clear()
    await update.message.reply_text("📝 Введи текст задачи:")
    return ASK_TASK_TEXT

async def received_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['task_title'] = update.message.text
    await update.message.reply_text("📅 Укажи дату выполнения (в формате ДД.ММ.ГГГГ):")
    return ASK_TASK_DATE

async def received_task_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_str = update.message.text.strip()
        date = datetime.strptime(date_str, "%d.%m.%Y").date()
        context.user_data['task_due'] = datetime.combine(date, datetime.min.time()).isoformat() + "Z"
        await update.message.reply_text("⏱ Сколько времени планируешь на выполнение? (например: 1 час, 30 минут)")
        return ASK_TASK_DURATION
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Попробуй снова (ДД.ММ.ГГГГ):")
        return ASK_TASK_DATE

async def received_task_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
    except HttpError as e:
        logger.error(f"Google API error: {e}")
        await update.message.reply_text("❌ Ошибка при работе с Google Tasks. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("❌ Произошла непредвиденная ошибка.")
    finally:
        context.user_data.clear()
    return ConversationHandler.END

# ... (остальные функции остаются такими же, как в предыдущей версии, но с добавлением обработки ошибок)

def main():
    # Проверяем наличие обязательных переменных окружения
    required_env_vars = ['TELEGRAM_TOKEN', 'GOOGLE_CREDENTIALS']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.critical(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
        return

    app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("today", today_tasks))
    app.add_handler(CommandHandler("overdue", overdue_tasks))
    app.add_handler(CommandHandler("listtasks", list_tasks))

    # Обработчики кнопок
    app.add_handler(MessageHandler(filters.Regex(r"^📋 Показать задачи$"), list_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^📆 Сегодня$"), today_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^⏰ Просроченные$"), overdue_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^❌ Отменить$"), cancel))

    # ConversationHandler для задач
    task_conv_handler = ConversationHandler(
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
    )

    # ConversationHandler для завершения задач
    done_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("done", done_start),
            MessageHandler(filters.Regex(r"^✅ Завершить задачу$"), done_start)
        ],
        states={
            ASK_DONE_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, mark_selected_done)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # ConversationHandler для событий
    event_conv_handler = ConversationHandler(
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
    )

    app.add_handler(task_conv_handler)
    app.add_handler(done_conv_handler)
    app.add_handler(event_conv_handler)

    # Обработчик ошибок
    app.add_error_handler(error_handler)

    logger.info("🚀 Бот запущен. Жду команды...")
    app.run_polling()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка при обработке сообщения: {context.error}", exc_info=context.error)
    
    if isinstance(context.error, telegram.error.Conflict):
        logger.critical("Обнаружен конфликт: уже запущен другой экземпляр бота!")
        os._exit(1)
    elif update:
        await update.message.reply_text("❌ Произошла ошибка. Пожалуйста, попробуйте позже.")

if __name__ == "__main__":
    main()
