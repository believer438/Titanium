import os
import threading
import traceback
import pandas as pd
import logging
from ta.trend import EMAIndicator
from core.binance_client import client
from core.trade_interface import open_trade, close_position
from core.trading_utils import get_leverage_from_file
from core.state import state
from core.telegram_controller import send_telegram
import time
import datetime

# Configs par défaut ou via variables d'environnement
symbol = os.getenv("EMA_SYMBOL", "ALGOUSDT")
interval = os.getenv("EMA_INTERVAL", "5m")
lookback = int(os.getenv("EMA_LOOKBACK", "100"))

_last_signal_lock = threading.Lock()
_last_signal = None
_last_ping = 0
_telegram_cooldown_lock = threading.Lock()
_telegram_last_sent = 0
TELEGRAM_COOLDOWN_SECONDS = 60

def can_send_telegram():
    global _telegram_last_sent
    with _telegram_cooldown_lock:
        now = time.time()
        if now - _telegram_last_sent > TELEGRAM_COOLDOWN_SECONDS:
            _telegram_last_sent = now
            return True
        return False

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
            # Envoi Telegram sur croisement haussier détecté
            if can_send_telegram():
                send_telegram("📈 Croisement EMA haussier détecté (bullish_cross)")
            return 'bullish_cross'
        else:
            return None
    else:
        if ema20_prev > ema50_prev and ema20_now < ema50_now:
            # Envoi Telegram sur croisement baissier détecté
            if can_send_telegram():
                send_telegram("📉 Croisement EMA baissier détecté (bearish_cross)")
            return 'bearish_cross'
        else:
            return None

def get_ema_values(live=False):
    """
    Récupère les EMA20 et EMA50 sur les données Binance, retourne le signal, le timestamp et les EMA.
    """
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=52)
        closes = [float(k[4]) for k in klines]
        if len(closes) < 50:
            msg = f"⏳ Pas assez de données EMA ({len(closes)} < 50)"
            logging.warning(msg)
            if can_send_telegram():
                send_telegram(msg)
            return None, None, None

        closes_series = pd.Series(closes)
        ema20 = closes_series.ewm(span=20, adjust=False).mean()
        ema50 = closes_series.ewm(span=50, adjust=False).mean()

        candle_close_time = int(klines[-2][6] // 1000)  # candle N-1
        signal = detect_ema_cross(ema20, ema50)
        return signal, candle_close_time, (ema20, ema50)

    except Exception as e:
        err_msg = f"❌ Erreur get_ema_values : {e}"
        logging.error(err_msg)
        traceback.print_exc()
        if can_send_telegram():
            send_telegram(err_msg)
        return None, None, None

def set_leverage_if_needed(new_leverage):
    try:
        client.futures_change_leverage(symbol=symbol, leverage=new_leverage)
        logging.info(f"🔧 Levier fixé à {new_leverage}x")
        if can_send_telegram():
            send_telegram(f"🔧 Levier fixé à {new_leverage}x")
    except Exception as e:
        err_msg = f"❌ Erreur changement levier : {e}"
        logging.error(err_msg)
        if can_send_telegram():
            send_telegram(err_msg)

def is_position_matching_direction(direction):
    try:
        if not state.position_open:
            return False
        return state.current_direction == direction
    except Exception as e:
        logging.error(f"⚠️ Erreur check position matching direction : {e}")
        return False

def execute_ema_cross_strategy(signal=None, candle_close_time=None):
    global _last_signal
    try:
        with _last_signal_lock:
            if signal is None or candle_close_time is None:
                return

            if _last_signal and signal == _last_signal[0] and candle_close_time == _last_signal[2]:
                return

            if state.position_open and not is_position_matching_direction(signal):
                logging.info(f"🔄 Fermeture position {state.current_direction} avant ouverture {signal}")
                close_position()
                time.sleep(1)
                state.reset_all()

            if is_position_matching_direction(signal):
                _last_signal = (signal, time.time(), candle_close_time)
                return

            leverage = get_leverage_from_file()
            set_leverage_if_needed(leverage)

            if signal in ("bullish_cross", "bullish"):
                send_telegram("✅ CONFIRMÉ 📈 Croisement haussier EMA à la clôture")
                open_trade("bullish")
            elif signal in ("bearish_cross", "bearish"):
                send_telegram("✅ CONFIRMÉ 📉 Croisement baissier EMA à la clôture")
                open_trade("bearish")

            _last_signal = (signal, time.time(), candle_close_time)

    except Exception as e:
        err_msg = f"❌ Erreur execute_ema_cross_strategy : {e}"
        logging.error(err_msg)
        traceback.print_exc()
        if can_send_telegram():
            send_telegram(err_msg)

def ema_live_watch_loop():
    last_live_signal = None
    logging.info("🚨 Surveillance EMA en temps réel (toutes les 5s) activée.")
    while True:
        try:
            _, _, (ema20, ema50) = get_ema_values()
            if ema20 is None or ema50 is None:
                time.sleep(5)
                continue

            signal = detect_ema_cross(ema20, ema50)

            # On trade dès qu'un croisement est détecté, même si la bougie n'est pas clôturée
            if signal and signal != last_live_signal:
                logging.info(f"⚡ Croisement EMA détecté en temps réel : {signal}")
                if can_send_telegram():
                    send_telegram(f"⚡ [INTRABOUGIE] Croisement EMA détecté : {signal}")
                last_live_signal = signal

                # On prend le timestamp de la dernière bougie clôturée pour la traçabilité
                klines = client.get_klines(symbol=symbol, interval=interval, limit=2)
                candle_close_time = int(klines[-2][6] // 1000)

                if signal == "bullish_cross":
                    execute_ema_cross_strategy("bullish", candle_close_time)
                elif signal == "bearish_cross":
                    execute_ema_cross_strategy("bearish", candle_close_time)

        except Exception as e:
            logging.error(f"Erreur dans la boucle EMA temps réel : {e}")
        time.sleep(5)


def start_ema_5m_loop():
    send_telegram("🚦 Boucle EMA 5m lancée !")
    global _last_ping
    while True:
        try:
            signal, candle_close_time, _ = get_ema_values()
            execute_ema_cross_strategy(signal, candle_close_time)

            if time.time() - _last_ping > 3600:
                send_telegram(" strategies 5m actif - en attente de croisement ...")
                _last_ping = time.time()

        except Exception as e:
            logging.error(f"Erreur boucle EMA 5m : {e}")
