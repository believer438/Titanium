import time
import logging
import traceback
import pandas as pd
from core.binance_client import client
from core.telegram_controller import send_telegram

# Assure-toi aussi que symbol et interval sont définis (ou importés)
symbol = "ALGOUSDT"  # ou importe depuis ta config si besoin
interval = "5m"      # ou importe depuis ta config si besoin

def track_ema_live_crossing():
    """
    Surveille en continu tout changement de position entre EMA20 et EMA50.
    Même un croisement temporaire est détecté.
    """
    logging.info("🚦 Surveillance ultra-réactive EMA20/EMA50 activée.")
    last_relation = None

    while True:
        try:
            klines = client.get_klines(symbol=symbol, interval=interval, limit=52)
            closes = [float(k[4]) for k in klines]
            if len(closes) < 50:
                logging.warning("⏳ Pas assez de données pour EMA tracking.")
                time.sleep(5)
                continue

            closes_series = pd.Series(closes)
            ema20 = closes_series.ewm(span=20, adjust=False).mean().iloc[-1]
            ema50 = closes_series.ewm(span=50, adjust=False).mean().iloc[-1]

            # Déterminer la relation actuelle
            if ema20 > ema50:
                current_relation = "above"
            elif ema20 < ema50:
                current_relation = "below"
            else:
                current_relation = "equal"

            # Vérifier s'il y a eu un changement
            if last_relation is not None and current_relation != last_relation:
                if current_relation == "above":
                    message = "📈 [TRACKER] EMA20 vient de passer au-dessus de EMA50 (croisement haussier détecté)"
                    logging.info(message)
                    if can_send_telegram():
                        send_telegram(message)
                elif current_relation == "below":
                    message = "📉 [TRACKER] EMA20 vient de passer en dessous de EMA50 (croisement baissier détecté)"
                    logging.info(message)
                    if can_send_telegram():
                        send_telegram(message)
                else:
                    message = "⚠️ [TRACKER] EMA20 égal à EMA50 (rare)"

                    logging.info(message)
                    if can_send_telegram():
                        send_telegram(message)

            last_relation = current_relation
            time.sleep(5)

        except Exception as e:
            logging.error(f"❌ Erreur dans track_ema_live_crossing : {e}")
            traceback.print_exc()
            if can_send_telegram():
                send_telegram(f"❌ Erreur EMA Tracker : {e}")
            time.sleep(5)
