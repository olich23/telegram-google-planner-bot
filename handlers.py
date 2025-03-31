from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, filters
from tasks import (
    list_tasks, addtask_start, received_task_text, received_task_date, received_task_duration,
    done_start, mark_selected_done, overdue_tasks, ASK_TASK_TEXT, ASK_TASK_DATE,
    ASK_TASK_DURATION, ASK_DONE_INDEX
)
from events import (
    addevent_start, received_event_title, received_event_date,
    received_event_start, received_event_end,
    ASK_EVENT_TITLE, ASK_EVENT_DATE, ASK_EVENT_START, ASK_EVENT_END
)
from today import today_tasks
from common import start, cancel

def get_handlers():
    handlers = []

    handlers.append(CommandHandler("start", start))
    handlers.append(CommandHandler("cancel", cancel))
    handlers.append(CommandHandler("listtasks", list_tasks))
    handlers.append(CommandHandler("today", today_tasks))
    handlers.append(CommandHandler("overdue", overdue_tasks))

    handlers.append(MessageHandler(filters.Regex(r"^📋 Показать задачи$"), list_tasks))
    handlers.append(MessageHandler(filters.Regex(r"^✅ Завершить задачу$"), done_start))
    handlers.append(MessageHandler(filters.Regex(r"^📆 Сегодня$"), today_tasks))
    handlers.append(MessageHandler(filters.Regex(r"^⏰ Просроченные$"), overdue_tasks))
    handlers.append(MessageHandler(filters.Regex(r"^❌ Отменить$"), cancel))

    add_task_conv = ConversationHandler(
        entry_points=[CommandHandler("addtask", addtask_start),
                      MessageHandler(filters.Regex(r"^📝 Добавить задачу$"), addtask_start)],
        states={
            ASK_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_text)],
            ASK_TASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_date)],
            ASK_TASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_duration)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    done_conv = ConversationHandler(
        entry_points=[CommandHandler("done", done_start)],
        states={ASK_DONE_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, mark_selected_done)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    add_event_conv = ConversationHandler(
        entry_points=[CommandHandler("addevent", addevent_start),
                      MessageHandler(filters.Regex(r"^📅 Добавить встречу$"), addevent_start)],
        states={
            ASK_EVENT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_title)],
            ASK_EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_date)],
            ASK_EVENT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_start)],
            ASK_EVENT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_event_end)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    handlers.extend([add_task_conv, done_conv, add_event_conv])
    return handlers
