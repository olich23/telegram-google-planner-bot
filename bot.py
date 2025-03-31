from telegram.ext import ApplicationBuilder
from handlers import setup_handlers
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
    setup_handlers(app)
    print("🚀 Бот запущен. Жду команды...")
    app.run_polling()

if __name__ == "__main__":
    main()
