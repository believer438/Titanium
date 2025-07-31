import time
import logging
import pandas as pd
from ta.trend import EMAIndicator
from dotenv import load_dotenv
import os
from binance.client import Client
from core.telegram_controller import send_telegram

# Charger .env
load_dotenv()

# Clés API
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

# Client Binance
client = Client(API_KEY, API_SECRET)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

SYMBOL = "ALGOUSDT"
INTERVAL = Client.KLINE_INTERVAL_5MINUTE

def get_klines(symbol, interval, limit=100):
    # Récupère les données de chandeliers (kline)
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    return df

def detect_cross(df):
    # Calcul des EMA20 et EMA50
    ema20 = EMAIndicator(close=df["close"], window=20).ema_indicator()
    ema50 = EMAIndicator(close=df["close"], window=50).ema_indicator()

    df["EMA20"] = ema20
    df["EMA50"] = ema50

    # Détection croisement entre les deux dernières valeurs
    if len(df) < 2:
        return None

    prev_ema20 = df["EMA20"].iloc[-2]
    prev_ema50 = df["EMA50"].iloc[-2]
    curr_ema20 = df["EMA20"].iloc[-1]
    curr_ema50 = df["EMA50"].iloc[-1]

    # Croisement haussier : EMA20 passe au-dessus de EMA50
    if prev_ema20 < prev_ema50 and curr_ema20 > curr_ema50:
        return "Croisement haussier détecté! EMA20 a croisé au-dessus de EMA50."

    # Croisement baissier : EMA20 passe en dessous de EMA50
    if prev_ema20 > prev_ema50 and curr_ema20 < curr_ema50:
        return "Croisement baissier détecté! EMA20 a croisé en dessous de EMA50."

    return None

def main():
    logging.info(f"Surveillance des croisements EMA20/EMA50 sur {SYMBOL} toutes les 1 minute...")
    send_telegram(f"Surveillance des croisements EMA20/EMA50 sur {SYMBOL} toutes les 1 minute...")

    last_cross = None

    # Premier check au lancement
    try:
        df = get_klines(SYMBOL, INTERVAL, limit=100)
        ema20 = EMAIndicator(close=df["close"], window=20).ema_indicator()
        ema50 = EMAIndicator(close=df["close"], window=50).ema_indicator()

        curr_ema20 = ema20.iloc[-1]
        curr_ema50 = ema50.iloc[-1]

        if curr_ema20 > curr_ema50:
            msg = f"EMA20 est au-dessus de EMA50 : tendance haussière"
            logging.info(msg)
            send_telegram(f"🔔 Démarrage: {msg} sur {SYMBOL}")
            last_cross = "haussier"
        else:
            msg = f"EMA20 est en dessous de EMA50 : tendance baissière"
            logging.info(msg)
            send_telegram(f"🔔 Démarrage: {msg} sur {SYMBOL}")
            last_cross = "baissier"
    except Exception as e:
        logging.error(f"Erreur au démarrage : {e}")
        send_telegram(f"⚠️ Erreur au démarrage : {e}")

    # Boucle de surveillance continue
    while True:
        try:
            df = get_klines(SYMBOL, INTERVAL, limit=100)
            message = detect_cross(df)
            if message:
                # Eviter les répétitions inutiles
                if ("haussier" in message and last_cross != "haussier") or \
                   ("baissier" in message and last_cross != "baissier"):
                    logging.info(message)
                    send_telegram(f"🚨 {message} sur {SYMBOL}")
                    last_cross = "haussier" if "haussier" in message else "baissier"
            time.sleep(60)
        except Exception as e:
            logging.error(f"Erreur: {e}")
            send_telegram(f"⚠️ Erreur durant la surveillance : {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
