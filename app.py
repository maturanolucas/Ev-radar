import os
import threading
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# env vars (defina no Render -> Environment Variables)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # opcional, para notificar um chat fixo

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN not set")
    raise SystemExit("Set TELEGRAM_TOKEN environment variable")

# setup Telegram (python-telegram-bot v13)
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher
bot = Bot(token=TELEGRAM_TOKEN)

# Example command
def start(update, context):
    update.message.reply_text("Ev-radar bot ativo ✅")

dispatcher.add_handler(CommandHandler("start", start))

# optional function to send a message to your chat id
def send_message_to_chat(text):
    if TELEGRAM_CHAT_ID:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

# start polling in background thread
def start_bot():
    logger.info("Starting Telegram long-polling...")
    updater.start_polling(drop_pending_updates=True)

threading.Thread(target=start_bot, daemon=True).start()

# Web endpoint (useful to check service health / webhook later)
@app.route("/", methods=["GET"])
def home():
    return "EV-Radar running", 200

if __name__ == "__main__":
    # bind to 0.0.0.0 and port provided by Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
