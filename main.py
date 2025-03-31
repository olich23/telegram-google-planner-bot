import logging
import os
from telegram.ext import ApplicationBuilder
from dotenv import load_dotenv
from handlers import get_handlers

logging.basicConfig(level=logging.INFO)
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Подключаем все обработчики
    handlers = get_handlers()
    for handler in handlers:
        app.add_handler(handler)

    logging.info("\ud83d\ude80 Бот запущен. Жду команды...")
    app.run_polling()


if __name__ == "__main__":
    main()
