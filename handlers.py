from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, filters
from tasks import *
from events import *

async def cancel(update, context):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

def setup_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listtasks", list_tasks))
    app.add_handler(CommandHandler("done", done_start))
    app.add_handler(CommandHandler("addtask", addtask_start))
    app.add_handler(CommandHandler("addevent", addevent_start))
    app.add_handler(MessageHandler(filters.Regex("^📋 Показать задачи$"), list_tasks))
    app.add_handler(MessageHandler(filters.Regex("^✅ Завершить задачу$"), done_start))
    app.add_handler(MessageHandler(filters.Regex("^📝 Добавить задачу$"), addtask_start))
    app.add_handler(MessageHandler(filters.Regex("^📅 Добавить встречу$"), addevent_start))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отменить$"), cancel))

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
        states={
            ASK_DONE_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, mark_selected_done)],
        },
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
