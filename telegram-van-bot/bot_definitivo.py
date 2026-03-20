import logging
import json
import os
import re
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from flask import Flask
from threading import Thread

# -------------------------
# Token del bot
# -------------------------
TOKEN = "8196791382:AAGmiVCPfOCNtaV0p2Qp0kwpZIBjSRYUs70"  # <- sostituisci con il tuo token reale

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------
# File dati utenti
# -------------------------
DB_FILE = "dati_dipendenti.json"
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        dipendenti = json.load(f)
else:
    dipendenti = {}

def salva_db():
    with open(DB_FILE, "w") as f:
        json.dump(dipendenti, f, indent=2)

# -------------------------
# Pulsante Reset globale
# -------------------------
def get_pulsante_reset():
    keyboard = [[InlineKeyboardButton("🔄 Reset flusso", callback_data="RESET_FLUSSO")]]
    return InlineKeyboardMarkup(keyboard)

# -------------------------
# Validazioni STAMPATELLO
# -------------------------
def nome_cognome_valido(testo):
    pattern = r'^[A-ZÀ-ÖØ-Þ ]+$'
    return bool(re.match(pattern, testo))

def targa_valida(testo, targhe_valide):
    testo = testo.upper()
    return testo in targhe_valide

# -------------------------
# Keep-alive per Replit
# -------------------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot attivo"

def run_web():
    app_web.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# -------------------------
# Funzione per inviare messaggio di benvenuto
# -------------------------
async def messaggio_benvenuto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Se vuoi aggiungere un'immagine/logo dell'azienda
    if os.path.exists("logo_azienda.png"):
        await update.message.reply_photo(
            photo=open("logo_azienda.png", "rb"),
            caption=f"✅ Ciao {user.first_name}! 👋\nBot pronto per il check del van assegnato.",
            reply_markup=get_pulsante_reset()
        )
    else:
        await update.message.reply_text(
            f"✅ Ciao {user.first_name}! 👋\nBot pronto per il check del van assegnato.",
            reply_markup=get_pulsante_reset()
        )

# -------------------------
# Gestione messaggi passo passo
# -------------------------
async def gestione_messaggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    testo = (update.message.text or "").strip().upper()
    oggi = date.today().strftime("%d/%m/%Y")

    # Inizializza utente
    if user_id not in dipendenti:
        dipendenti[user_id] = {"benvenuto": False, "ultimo_giorno": "", "passo_corrente": 1, "dati": {}}
    utente = dipendenti[user_id]

    # Messaggio iniziale
    if not utente["benvenuto"] or utente["ultimo_giorno"] != oggi:
        await messaggio_benvenuto(update, context)
        utente["benvenuto"] = True
        utente["ultimo_giorno"] = oggi
        utente["passo_corrente"] = 1
        utente["dati"] = {}
        salva_db()

    passo = utente["passo_corrente"]

    # Passo 1: Data
    if passo == 1 and "data_proposta" not in utente["dati"]:
        utente["dati"]["data_proposta"] = oggi
        keyboard = [[InlineKeyboardButton("Sì", callback_data="CONFERMA_DATA")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"📅 La data di oggi è {oggi}. Confermi?", reply_markup=reply_markup)
        salva_db()
        return

    # Passo 2: Nome e Cognome
    if passo == 2:
        if nome_cognome_valido(testo):
            utente["dati"]["nome_cognome"] = testo.upper()
            utente["passo_corrente"] = 3
            await update.message.reply_text("Passo 3: Inserisci la targa del VAN")
        else:
            await update.message.reply_text("❌ Nome e Cognome non valido. Usa solo lettere e spazi.")

    # Passo 3: Targa VAN
    elif passo == 3:
        if os.path.exists("targhe.txt"):
            with open("targhe.txt", "r") as f:
                targhe_valide = [line.strip().upper() for line in f if line.strip()]
        else:
            targhe_valide = []

        if targa_valida(testo, targhe_valide):
            utente["dati"]["targa"] = testo.upper()
            utente["passo_corrente"] = 4
            await update.message.reply_text("Passo 4: Invia il video o file")
        else:
            await update.message.reply_text("❌ Targa non valida!")

    # Passo 4: Video/File
    elif passo == 4:
        if update.message.document or update.message.video:
            utente["dati"]["file"] = "Ricevuto"
            utente["passo_corrente"] = 1
            salva_db()
            await update.message.reply_text("✅ Tutto registrato correttamente. Buon lavoro!", reply_markup=get_pulsante_reset())
            
            # Riavvia flusso automaticamente
            class FakeMessage:
                def __init__(self, user, chat_id):
                    self.text = " "
                    self.chat_id = chat_id
                    self.from_user = user
                async def reply_text(self, *args, **kwargs):
                    await update.message.reply_text(*args, **kwargs)
            fake_update = Update(update.update_id, message=FakeMessage(user, update.message.chat_id))
            await gestione_messaggi(fake_update, context)
        else:
            await update.message.reply_text("❌ Per favore invia un video o file valido.")

# -------------------------
# Callback conferma data
# -------------------------
async def conferma_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Data confermata!")

    user_id = str(query.from_user.id)
    if user_id in dipendenti:
        utente = dipendenti[user_id]
        utente["dati"]["data"] = utente["dati"].get("data_proposta", "")
        utente["passo_corrente"] = 2
        salva_db()
        await query.message.reply_text(f"✅ Data confermata: {utente['dati']['data']}")
        await query.message.reply_text("Passo 2: Inserisci Nome e Cognome")

# -------------------------
# Callback RESET
# -------------------------
async def callback_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    dipendenti[user_id] = {"benvenuto": False, "ultimo_giorno": "", "passo_corrente": 1, "dati": {}}
    salva_db()
    await query.edit_message_text("🔄 Flusso COMPLETAMENTE resettato. Ricomincia dal Passo 1!")

    # Messaggio di benvenuto
    user = query.from_user
    await messaggio_benvenuto(update, context)

    # Riavvia flusso passo 1 automaticamente
    class FakeMessage:
        def __init__(self, user, chat_id):
            self.text = " "
            self.chat_id = chat_id
            self.from_user = user
        async def reply_text(self, *args, **kwargs):
            await query.message.reply_text(*args, **kwargs)
    fake_update = Update(update.update_id, message=FakeMessage(user, query.message.chat_id))
    await gestione_messaggi(fake_update, context)

# -------------------------
# Avvio bot
# -------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, gestione_messaggi))
    app.add_handler(CallbackQueryHandler(conferma_data, pattern="CONFERMA_DATA"))
    app.add_handler(CallbackQueryHandler(callback_reset, pattern="RESET_FLUSSO"))

    keep_alive()  # mantiene il bot attivo su Replit
    print("🤖 Bot pronto, in attesa di utenti...")
    app.run_polling()

if __name__ == "__main__":
    main()
