from telegram.ext import CommandHandler, ConversationHandler, MessageHandler, filters

from tasks import (
    addtask_start, received_task_text, received_task_date, received_task_duration,
    list_tasks, done_start, mark_selected_done
)

from events import (
    addevent_start, received_event_title, received_event_date,
    received_event_start, received_event_end
)

from today import today_tasks
from overdue import overdue_tasks
from utils import cancel, start

ASK_TASK_TEXT = 0
ASK_TASK_DATE = 1
ASK_TASK_DURATION = 2
ASK_DONE_INDEX = 3
ASK_EVENT_TITLE = 4
ASK_EVENT_DATE = 5
ASK_EVENT_START = 6
ASK_EVENT_END = 7

def get_handlers():
    handlers = [
        CommandHandler("start", start),
        CommandHandler("cancel", cancel),
        CommandHandler("listtasks", list_tasks),
        CommandHandler("done", done_start),
        CommandHandler("addevent", addevent_start),
        CommandHandler("today", today_tasks),
        CommandHandler("overdue", overdue_tasks),

        MessageHandler(filters.Regex(r"^\U0001F4DD Добавить задачу$"), addtask_start),
        MessageHandler(filters.Regex(r"^\U0001F4CB Показать задачи$"), list_tasks),
        MessageHandler(filters.Regex(r"^\u2705 Завершить задачу$"), done_start),
        MessageHandler(filters.Regex(r"^\U0001F4C5 Добавить встречу$"), addevent_start),
        MessageHandler(filters.Regex(r"^\U0001F4C6 Сегодня$"), today_tasks),
        MessageHandler(filters.Regex(r"^\u23F0 Просроченные$"), overdue_tasks),
        MessageHandler(filters.Regex(r"^\u274C Отменить$"), cancel),

        ConversationHandler(
            entry_points=[CommandHandler("addtask", addtask_start)],
            states={
                ASK_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_text)],
                ASK_TASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_date)],
                ASK_TASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_duration)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            allow_reentry=True
        ),

        ConversationHandler(
            entry_points=[CommandHandler("done", done_start)],
            states={
                ASK_DONE_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, mark_selected_done)]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            allow_reentry=True
        ),

        ConversationHandler(
            entry_points=[CommandHandler("addevent", addevent_start)],
            states={
                ASK_EVENT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_title)],
                ASK_EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_date)],
                ASK_EVENT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_start)],
                ASK_EVENT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_end)]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            allow_reentry=True
        )
    ]

    return handlers
