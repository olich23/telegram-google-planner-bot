from telegram.ext import CommandHandler, MessageHandler, filters, ConversationHandler
from telegram import Update
from contextlib import suppress

from events import (
    addevent_start,
    received_event_title,
    received_event_date,
    received_event_start,
    received_event_end
)
from tasks import (
    addtask_start,
    received_task_text,
    received_task_date,
    received_task_duration,
    done_start,
    mark_selected_done,
    overdue_tasks,
    today_tasks
)
from common import cancel, start, list_tasks
from tasks import ASK_TASK_TEXT, ASK_TASK_DATE, ASK_TASK_DURATION, ASK_DONE_INDEX
from events import ASK_EVENT_TITLE, ASK_EVENT_DATE, ASK_EVENT_START, ASK_EVENT_END

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("listtasks", list_tasks))
    app.add_handler(CommandHandler("today", today_tasks))
    app.add_handler(CommandHandler("overdue", overdue_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"^\ud83d\udcdb Показать задачи$"), list_tasks))

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

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("done", done_start)],
        states={ASK_DONE_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, mark_selected_done)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    ))

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
