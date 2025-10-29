import os
import time
import requests
from flask import Flask
from telegram import Bot

app = Flask(__name__)

# Variáveis de ambiente (Render → Environment)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)

@app.route('/')
def home():
    return "EV-Radar bot está rodando com sucesso!"

def send_message(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def check_updates():
    # Exemplo simples — você pode adaptar pra sua lógica
    url = "https://api.sofascore.com/api/v1/unique-tournament/17/season/54586/events"  
    response = requests.get(url)
    if response.status_code == 200:
        send_message("EV-Radar está ativo e monitorando eventos!")
    else:
        send_message("Falha ao buscar dados da API.")

if __name__ == '__main__':
    # Se estiver rodando localmente, execute Flask
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
