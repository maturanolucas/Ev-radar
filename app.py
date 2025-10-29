import os
import threading
import logging
from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler

# Configuração de logs (opcional, mas útil para debug)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cria o app Flask (necessário para Render)
app = Flask(__name__)

# Variáveis de ambiente (Render → Environment)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # opcional

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN não configurado")
    raise SystemExit("Defina TELEGRAM_TOKEN nas variáveis de ambiente do Render")

# --- Verificação do imghdr (pode ser imghdr-py no requirements) ---
try:
    import imghdr  # noqa: E402
except ModuleNotFoundError:
    IMGHDR_AVAILABLE = False
    logger.error("❌ imghdr NÃO encontrado. Verifique se 'imghdr-py' está no requirements.txt")
else:
    IMGHDR_AVAILABLE = True
    logger.info("✅ imghdr importado com sucesso.")

# Configura o bot do Telegram
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher
bot = Bot(token=TELEGRAM_TOKEN)

# Comando /start para testar o bot
def start(update, context):
    update.message.reply_text("✅ EV-Radar bot está ativo e rodando!")

dispatcher.add_handler(CommandHandler("start", start))

# Função opcional para enviar mensagens automáticas ao chat configurado
def send_message_to_chat(text):
    if TELEGRAM_CHAT_ID:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
    else:
        logger.warning("TELEGRAM_CHAT_ID não definido; mensagem não enviada.")

# Thread separada para rodar o bot (polling)
def start_bot():
    logger.info("🚀 Iniciando o bot do Telegram (long polling)...")
    updater.start_polling(drop_pending_updates=True)

# Inicia o bot em background
threading.Thread(target=start_bot, daemon=True).start()

# Endpoint simples para o Flask responder requisições (usado pelo Render)
@app.route("/", methods=["GET"])
def home():
    return "EV-Radar está rodando corretamente! ✅", 200

# Endpoint para checar se imghdr está disponível
@app.route("/check-imghdr", methods=["GET"])
def check_imghdr():
    """
    Retorna JSON indicando se o módulo imghdr está presente no ambiente.
    Use isso para checar rapidamente no Render.
    """
    return jsonify({
        "imghdr_available": IMGHDR_AVAILABLE
    }), 200 if IMGHDR_AVAILABLE else 500

# Inicia o servidor Flask na porta do Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Servidor Flask rodando na porta {port}")
    app.run(host="0.0.0.0", port=port)
