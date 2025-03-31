import logging
from telegram.ext import ApplicationBuilder
from telegram.ext import CommandHandler, MessageHandler, filters, ConversationHandler

from auth import get_credentials
from handlers import (
    start, cancel, list_tasks, overdue_tasks, today_tasks,
    addtask_start, received_task_text, received_task_date, received_task_duration,
    done_start, mark_selected_done,
    addevent_start, received_event_title, received_event_date, received_event_start, received_event_end,
    ASK_TASK_TEXT, ASK_TASK_DATE, ASK_TASK_DURATION,
    ASK_DONE_INDEX,
    ASK_EVENT_TITLE, ASK_EVENT_DATE, ASK_EVENT_START, ASK_EVENT_END
)

import os
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)

app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

# Команды
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(CommandHandler("listtasks", list_tasks))
app.add_handler(CommandHandler("overdue", overdue_tasks))
app.add_handler(CommandHandler("today", today_tasks))

# Кнопки
app.add_handler(MessageHandler(filters.Regex(r"^\ud83d\udccb Показать задачи$"), list_tasks))
app.add_handler(MessageHandler(filters.Regex(r"^\ud83d\udd22 Просроченные$"), overdue_tasks))
app.add_handler(MessageHandler(filters.Regex(r"^\ud83d\udcc6 Сегодня$"), today_tasks))
app.add_handler(MessageHandler(filters.Regex(r"^\ud83d\udcdd Добавить задачу$"), addtask_start))
app.add_handler(MessageHandler(filters.Regex(r"^\ud83d\udcc5 Добавить встречу$"), addevent_start))
app.add_handler(MessageHandler(filters.Regex(r"^\u2705 Завершить задачу$"), done_start))
app.add_handler(MessageHandler(filters.Regex(r"^\u274c Отменить$"), cancel))

# Диалог добавления задачи
app.add_handler(ConversationHandler(
    entry_points=[CommandHandler("addtask", addtask_start)],
    states={
        ASK_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_text)],
        ASK_TASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_date)],
        ASK_TASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_duration)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
))

# Диалог завершения задачи
app.add_handler(ConversationHandler(
    entry_points=[CommandHandler("done", done_start)],
    states={ASK_DONE_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, mark_selected_done)]},
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
))

# Диалог добавления встречи
app.add_handler(ConversationHandler(
    entry_points=[CommandHandler("addevent", addevent_start)],
    states={
        ASK_EVENT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_title)],
        ASK_EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_date)],
        ASK_EVENT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_start)],
        ASK_EVENT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_end)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
))

print("\ud83d\ude80 \u0411\u043e\u0442 \u0437\u0430\u043f\u0443\u0449\u0435\u043d. \u0416\u0434\u0443 \u043a\u043e\u043c\u0430\u043d\u0434\u044b...")
app.run_polling()
