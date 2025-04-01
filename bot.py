# bot.py
import logging
import pickle
import os
import io
import base64
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
    if encoded_token:
        try:
            token_data = base64.b64decode(encoded_token)
            creds = pickle.load(io.BytesIO(token_data))
        except Exception as e:
            logging.error(f"Ошибка загрузки токена: {e}")
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_config(
            eval(os.getenv("GOOGLE_CREDENTIALS")), SCOPES
        )
        creds = flow.run_local_server(port=0)
    return creds

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
    except Exception as e:
        logger.error(f"Ошибка при добавлении задачи: {e}")
        await update.message.reply_text("❌ Произошла ошибка при добавлении задачи. Попробуй снова.")
    finally:
        context.user_data.clear()
    return ConversationHandler.END

async def done_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
            due = task.get('due', '')
            if due:
                try:
                    due_dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ")
                    due_str = due_dt.strftime("%d.%m.%Y")
                except:
                    due_str = due[:10]
                message += f"{idx}. {task['title']} (до {due_str})\n"
            else:
                message += f"{idx}. {task['title']}\n"
                
        await update.message.reply_text(message)
        return ASK_DONE_INDEX
    except Exception as e:
        logger.error(f"Ошибка в done_start: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй снова.")
        return ConversationHandler.END

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
    finally:
        context.user_data.clear()
    return ConversationHandler.END

async def today_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        creds = get_credentials()
        now = datetime.now(MINSK_TZ)
        today_str = now.date()

        # Получаем задачи
        service = build("tasks", "v1", credentials=creds)
        result = service.tasks().list(tasklist='@default', showCompleted=False).execute()
        tasks = result.get('items', [])

        today_list = []
        for task in tasks:
            due = task.get("due")
            if due:
                try:
                    due_dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).astimezone(MINSK_TZ)
                    if due_dt.date() == today_str:
                        today_list.append(f"• {task['title']} (до {due_dt.strftime('%H:%M')})")
                except Exception:
                    try:
                        due_date = datetime.strptime(due[:10], "%Y-%m-%d").date()
                        if due_date == today_str:
                            today_list.append(f"• {task['title']} (на сегодня)")
                    except Exception as e:
                        logger.warning(f"Ошибка обработки даты задачи: {e}")

        # Получаем события календаря
        calendar_service = build("calendar", "v3", credentials=creds)
        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=now.replace(hour=0, minute=0, second=0).isoformat(),
            timeMax=(now + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        # Формируем сообщение
        lines = ["📆 Задачи и встречи на сегодня:"]
        lines.extend(today_list if today_list else ["Задач нет"])

        if events:
            lines.append("\n🕒 Встречи:")
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'Без названия')
                if 'T' in start:
                    start_dt = datetime.fromisoformat(start).astimezone(MINSK_TZ)
                    lines.append(f"• {summary} в {start_dt.strftime('%H:%M')}")
                else:
                    lines.append(f"• {summary} (весь день)")
        else:
            lines.append("\nВстреч нет")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"Ошибка в today_tasks: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении данных.")

async def overdue_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
                        overdue.append(f"❗ {task['title']} (просрочено {due_dt.strftime('%d.%m.%Y %H:%M')})")
                except Exception:
                    try:
                        due_date = datetime.strptime(due[:10], "%Y-%m-%d").date()
                        if due_date < now.date():
                            overdue.append(f"❗ {task['title']} (просрочено {due_date.strftime('%d.%m.%Y')})")
                    except Exception as e:
                        logger.warning(f"Ошибка обработки даты: {e}")
                        continue

        if overdue:
            await update.message.reply_text("⏰ Просроченные задачи:\n" + "\n".join(overdue))
        else:
            await update.message.reply_text("✅ У тебя нет просроченных задач!")
    except Exception as e:
        logger.error(f"Ошибка в overdue_tasks: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении данных.")

async def addevent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📌 Введи название встречи:")
    return ASK_EVENT_TITLE

async def received_event_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event_title'] = update.message.text
    await update.message.reply_text("📅 Укажи дату встречи (ДД.ММ.ГГГГ):")
    return ASK_EVENT_DATE

async def received_event_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_str = update.message.text.strip()
        datetime.strptime(date_str, "%d.%m.%Y")  # Проверка формата
        context.user_data['event_date'] = date_str
        await update.message.reply_text("🕒 Укажи время начала (например: 14:30):")
        return ASK_EVENT_START
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Попробуй снова (ДД.ММ.ГГГГ):")
        return ASK_EVENT_DATE

async def received_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        time_str = update.message.text.strip()
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
            raise ValueError
        context.user_data['event_start'] = time_str
        await update.message.reply_text("🕕 Укажи время окончания (например: 15:30):")
        return ASK_EVENT_END
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени. Попробуй снова (ЧЧ:ММ):")
        return ASK_EVENT_START

async def received_event_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        time_str = update.message.text.strip()
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
            raise ValueError

        title = context.user_data['event_title']
        date_str = context.user_data['event_date']
        start_time = context.user_data['event_start']
        end_time = time_str

        start_dt = datetime.strptime(f"{date_str} {start_time}", "%d.%m.%Y %H:%M")
        end_dt = datetime.strptime(f"{date_str} {end_time}", "%d.%m.%Y %H:%M")

        if end_dt <= start_dt:
            await update.message.reply_text("❌ Время окончания должно быть позже времени начала. Попробуй снова:")
            return ASK_EVENT_END

        event = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/Minsk'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Europe/Minsk'},
            'description': 'Добавлено через Telegram-бота'
        }

        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        service.events().insert(calendarId='primary', body=event).execute()

        await update.message.reply_text(f"✅ Встреча '{title}' добавлена в календарь на {date_str} с {start_time} до {end_time}!")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени. Попробуй снова (ЧЧ:ММ):")
        return ASK_EVENT_END
    except Exception as e:
        logger.error(f"Ошибка при добавлении события: {e}")
        await update.message.reply_text(f"❌ Ошибка при добавлении события: {e}")
    finally:
        context.user_data.clear()
    return ConversationHandler.END

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
            due = task.get('due', '')
            
            if due:
                try:
                    due_dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ")
                    due_str = due_dt.strftime("%d.%m.%Y %H:%M")
                except:
                    due_str = due[:10]
                message += f"{idx}. {title} (до {due_str})"
            else:
                message += f"{idx}. {title}"
                
            if notes:
                message += f" — {notes}"
            message += "\n"
            
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Ошибка в list_tasks: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении задач.")

def main():
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("today", today_tasks))
    app.add_handler(CommandHandler("overdue", overdue_tasks))

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

    logger.info("🚀 Бот запущен. Жду команды...")
    app.run_polling()

if __name__ == "__main__":
    main()
