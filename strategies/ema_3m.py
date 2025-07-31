import pandas as pd
from ta.trend import EMAIndicator
from core.binance_client import client
from binance.client import Client
from core.telegram_controller import send_telegram
from strategies.ema_cross import execute_ema_cross_strategy
from core.state import state
import time
import logging
import datetime

symbol = "ALGOUSDT"

_last_processed_candle = 0
_last_ping = 0
_last_telegram_sent = 0
_last_signal_time = 0
_last_signal_type = None
TELEGRAM_COOLDOWN_SECONDS = 60

def can_send_telegram():
    global _last_telegram_sent
    now = time.time()
    if now - _last_telegram_sent > TELEGRAM_COOLDOWN_SECONDS:
        _last_telegram_sent = now
        return True
    return False

def get_ema(symbol, interval, length=60):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=length)
        if len(klines) < 50:
            msg = f"⚠️ Pas assez de données klines pour {symbol} en {interval}. Reçu: {len(klines)}"
            logging.warning(msg)
            if can_send_telegram():
                send_telegram(msg)
            return None, None
        closes = [float(k[4]) for k in klines]
        closes_series = pd.Series(closes)
        ema20 = EMAIndicator(closes_series, window=20).ema_indicator()
        ema50 = EMAIndicator(closes_series, window=50).ema_indicator()
        return ema20, ema50
    except Exception as e:
        msg = f"❌ Erreur dans get_ema: {e}"
        logging.error(msg)
        if can_send_telegram():
            send_telegram(msg)
        return None, None

def detect_ema_cross(ema_short, ema_long, bullish=True):
    """
    Détecte les croisements EMA20 / EMA50 dans deux séries pandas.
    Renvoie 'bullish_cross', 'bearish_cross' ou None.
    """
    if len(ema_short) < 2 or len(ema_long) < 2:
        return None

    ema20_now = ema_short.iloc[-1]
    ema50_now = ema_long.iloc[-1]
    ema20_prev = ema_short.iloc[-2]
    ema50_prev = ema_long.iloc[-2]

    if bullish:
        if ema20_prev < ema50_prev and ema20_now > ema50_now:
            if can_send_telegram():
                send_telegram("📈 Croisement EMA haussier détecté (bullish_cross)")
            return 'bullish_cross'
        else:
            return None
    else:
        if ema20_prev > ema50_prev and ema20_now < ema50_now:
            if can_send_telegram():
                send_telegram("📉 Croisement EMA baissier détecté (bearish_cross)")
            return 'bearish_cross'
        else:
            return None

def ema_live_watch_loop():
    """
    Surveillance EMA en temps réel (toutes les 5s) :
    - Détecte et traite tous les croisements EMA, même ceux qui n'existent qu'en intrabougie.
    - Notifie et trade dès qu'un croisement est détecté, même si la bougie n'est pas clôturée.
    - Vérifie la tendance 5m avant de trader.
    ⚠️ Attention : cette méthode augmente le risque de faux signaux (croisements éphémères).
    """
    last_live_signal = None
    logging.info("🚨 Surveillance EMA en temps réel (toutes les 5s) activée.")
    while True:
        try:
            # Récupère les EMA sur le timeframe principal (3m)
            _, _, (ema20, ema50) = get_ema_values()
            if ema20 is None or ema50 is None:
                time.sleep(5)
                continue

            # Récupère aussi les EMA du timeframe supérieur pour la tendance (5m)
            klines_5m = client.get_klines(symbol=symbol, interval="5m", limit=52)
            closes_5m = [float(k[4]) for k in klines_5m]
            closes_series_5m = pd.Series(closes_5m)
            ema20_5m = closes_series_5m.ewm(span=20, adjust=False).mean()
            ema50_5m = closes_series_5m.ewm(span=50, adjust=False).mean()
            bullish_trend = ema20_5m.iloc[-1] > ema50_5m.iloc[-1]
            bearish_trend = ema20_5m.iloc[-1] < ema50_5m.iloc[-1]

            signal = detect_ema_cross(ema20, ema50)

            # On trade dès qu'un croisement est détecté, même si la bougie n'est pas clôturée,
            # mais seulement si la tendance 5m est alignée
            if signal and signal != last_live_signal:
                logging.info(f"⚡ Croisement EMA détecté en temps réel : {signal}")
                if can_send_telegram():
                    send_telegram(f"⚡ [INTRABOUGIE] Croisement EMA détecté : {signal}")
                last_live_signal = signal

                klines = client.get_klines(symbol=symbol, interval=interval, limit=2)
                candle_close_time = int(klines[-2][6] // 1000)

                if signal == "bullish_cross" and bullish_trend:
                    execute_ema_cross_strategy("bullish", candle_close_time)
                elif signal == "bearish_cross" and bearish_trend:
                    execute_ema_cross_strategy("bearish", candle_close_time)
                else:
                    logging.info("❌ Croisement détecté mais tendance 5m non alignée, aucun trade.")

        except Exception as e:
            logging.error(f"Erreur dans la boucle EMA temps réel : {e}")
        time.sleep(5)
        
def start_ema_3m_loop():
    """
    Lance la surveillance EMA 3m avec confirmation à la clôture et tendance 5m.
    À appeler depuis main.py dans un thread.
    """
    logging.info("🚦 Boucle EMA 3m lancée et active !")
    send_telegram("🚦 Boucle EMA 3m lancée et active !")
    ema_live_watch_loop()