import os
import time
import threading
import traceback
import gc
import logging
import psutil
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from dotenv import load_dotenv
from core.state import state
from core.telegram_controller import stop_telegram_bot, send_telegram
from core.config import (
    symbol,
    default_leverage,
    default_quantity_usdt,
    stop_loss_pct,
    take_profit_pct,
    BASE_DIR,
    MODE_FILE,
    GAIN_ALERT_FILE
)
from core.binance_client import client, check_position_open, change_leverage
from core.trade_interface import open_trade, close_position
from core.position_utils import sync_position
from core.trailing import update_trailing_sl_and_tp, wait_for_tp_or_exit
from core.utils import safe_round, retry_order
from core.trading_utils import calculate_quantity, log_trade, get_mode, get_leverage_from_file
import subprocess
import math

# === Chargement des variables d’environnement (.env) ===
load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

# === VARIABLES GLOBALES ===
trailing_thread = None
tp_thread = None
stop_event = threading.Event()
last_bot_tp = None
last_bot_sl = None
position_lock = threading.Lock()
threads = []

logging.basicConfig(
    filename='bot.log',
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_system_usage():
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent()
    logging.warning(f"RAM utilisée : {mem.percent}% | CPU : {cpu}%")

def check_futures_permissions():
    try:
        account_info = client.futures_account()
        if "canTrade" not in account_info or not account_info["canTrade"]:
            raise Exception("⚠ Les Futures ne sont pas activés sur ce compte Binance.")
            logging.warning("✅ Futures activés sur ce compte Binance.")
    except Exception as e:
        logging.error(f"❌ Erreur de permission Futures : {e}")
        raise

def sync_time():
    try:
        server_time = client.get_server_time()["serverTime"] // 1000
        local_time = int(time.time())
        delta = server_time - local_time
        if abs(delta) > 2:
            logging.warning(f"⚠️ Décalage horaire détecté : {delta} secondes (Synchronisez l'horloge Windows !)")
        else:
            logging.info("⏰ Heure locale synchronisée avec Binance.")
    except Exception as e:
        logging.error(f"Erreur lors de la synchronisation de l'heure : {e}")

def sync_windows_time():
    try:
        subprocess.run("w32tm /resync", shell=True, check=True)
        logging.info("⏰ Synchronisation de l'heure Windows effectuée.")
    except Exception as e:
        logging.error(f"Erreur lors de la synchronisation de l'heure Windows : {e}")
        send_telegram(f"⚠️ Erreur synchronisation heure Windows : {e}")

def get_price_precision(symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            tick_size = float([f for f in s['filters'] if f['filterType'] == 'PRICE_FILTER'][0]['tickSize'])
            return int(round(-math.log10(tick_size)))
    return 4

def auto_set_sl_tp(stop_event):
    while not stop_event.is_set():
        try:
            positions = client.futures_position_information(symbol=symbol)
            position_handled = False

            for pos in positions:
                amt = float(pos['positionAmt'])

                if amt != 0 and not position_handled:
                    position_handled = True

                    try:
                        account_info = client.futures_account()
                        current_leverage = default_leverage
                        for asset in account_info['positions']:
                            if asset['symbol'] == symbol:
                                current_leverage = int(asset.get('leverage', default_leverage))
                                break
                        client.futures_change_leverage(symbol=symbol, leverage=current_leverage)
                    except Exception as e:
                        logging.error(f"⚠️ Erreur application du levier : {e}")
                        send_telegram(f"⚠️ Erreur application du levier : {e}")

                    state.position_open = True
                    entry_price = float(pos['entryPrice'])
                    state.current_entry_price = entry_price
                    direction = "bullish" if amt > 0 else "bearish"
                    state.current_direction = direction
                    qty = abs(amt)
                    state.current_quantity = qty

                    side_close = "SELL" if direction == "bullish" else "BUY"
                    take_profit = entry_price * (1 + take_profit_pct if amt > 0 else 1 - take_profit_pct)
                    stop_price = entry_price * (1 - stop_loss_pct if amt > 0 else 1 + stop_loss_pct)

                    precision = get_price_precision(symbol)
                    stop_price = round(stop_price, precision)
                    take_profit = round(take_profit, precision)

                    orders = client.futures_get_open_orders(symbol=symbol)
                    sl_orders = [o for o in orders if o['type'] == "STOP_MARKET" and o['side'] == side_close and o.get('closePosition', False)]
                    tp_orders = [o for o in orders if o['type'] == "TAKE_PROFIT_MARKET" and o['side'] == side_close and o.get('closePosition', False)]

                    has_sl = len(sl_orders) > 0
                    has_tp = len(tp_orders) > 0

                    logging.info(f"Positions: {amt}, SL orders found: {len(sl_orders)}, TP orders found: {len(tp_orders)}")
                    logging.info(f"Has SL: {has_sl}, Has TP: {has_tp}")

                    if not has_tp:
                        retry_order(lambda: client.futures_create_order(
                            symbol=symbol,
                            side=side_close,
                            type="TAKE_PROFIT_MARKET",
                            stopPrice=take_profit,
                            closePosition=True,
                            timeInForce="GTC"
                        ))
                        global last_bot_tp
                        last_bot_tp = take_profit
                        send_telegram(f"🎯Take profit automatique à {take_profit}$")

                    if not has_sl:
                        retry_order(lambda: client.futures_create_order(
                            symbol=symbol,
                            side=side_close,
                            type="STOP_MARKET",
                            stopPrice=stop_price,
                            closePosition=True,
                            timeInForce="GTC"
                        ))
                        global last_bot_sl
                        last_bot_sl = stop_price
                        send_telegram(f"🛡 Stop loss automatique à {stop_price}$")

            if not position_handled:
                state.position_open = False
                state.current_entry_price = None
                state.current_direction = None
                state.current_quantity = None

            gc.collect()
            time.sleep(3)

        except Exception as e:
            logging.error(f"❌ Erreur dans auto_set_sl_tp : {e}")
            send_telegram(f"❌ Erreur dans auto_set_sl_tp : {e}")
            gc.collect()
            time.sleep(3)

def should_stop():
    stop_path = os.path.join(BASE_DIR, "stop.txt")
    return os.path.exists(stop_path)

def update_status(text):
    try:
        status_path = os.path.join(BASE_DIR, "status.txt")
        with open(status_path, "w") as f:
            f.write(text)
    except Exception as e:
        logging.error(f"Erreur écriture status.txt : {e}")

def manual_close_requested():
    manual_close_path = os.path.join(BASE_DIR, "manual_close_request.txt")
    return os.path.exists(manual_close_path)

def reset_manual_close():
    manual_close_path = os.path.join(BASE_DIR, "manual_close_request.txt")
    if os.path.exists(manual_close_path):
        os.remove(manual_close_path)

def manual_close_watcher(stop_event):
    while not stop_event.is_set():
        if manual_close_requested():
            try:
                close_position()
            except Exception as e:
                send_telegram(f"❌ Erreur lors de la fermeture manuelle : {e}")
                logging.error(f"❌ Erreur lors de la fermeture manuelle : {e}")
            reset_manual_close()
        gc.collect()
        time.sleep(0.1)

def monitor_position(stop_event):
    global last_bot_tp, last_bot_sl
    last_position_amt = None
    last_detected_tp = None
    last_detected_sl = None

    while not stop_event.is_set():
        try:
            positions = client.futures_position_information(symbol=symbol)
            detected = False
            for pos in positions:
                if float(pos['positionAmt']) != 0:
                    detected = True
                    with position_lock:
                        if not state.position_open:
                            send_telegram("⚠ Une position a été détectée ouverte manuellement sur Binance.")
                        state.position_open = True
                        state.current_entry_price = float(pos['entryPrice'])
                        state.current_direction = "bullish" if float(pos['positionAmt']) > 0 else "bearish"
                        state.current_quantity = abs(float(pos['positionAmt']))
                    logging.info(f"[monitor_position] Position détectée : {pos['positionAmt']} @ {pos['entryPrice']}")
                    orders = client.futures_get_open_orders(symbol=symbol)
                    tp = None
                    sl = None
                    for order in orders:
                        if order['type'] == "TAKE_PROFIT_MARKET":
                            tp = float(order['stopPrice'])
                        if order['type'] == "STOP_MARKET":
                            sl = float(order['stopPrice'])
                    last_position_amt = float(pos['positionAmt'])
                    break
            if not detected:
                with position_lock:
                    if state.position_open:
                        logging.info("[monitor_position] Reset de la position (aucune position détectée)")
                        state.reset_all()
                        last_detected_tp = None
                        last_detected_sl = None
                        last_position_amt = None
            gc.collect()
            time.sleep(1)
        except Exception as e:
            logging.error(f"Erreur dans monitor_position : {e}")
            traceback.print_exc()
            gc.collect()
            time.sleep(10)

def is_another_bot_running(lock_file):
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                if lock_file in ' '.join(proc.info['cmdline']):
                    return True
        except Exception:
            continue
    return False

def run_bot():
    send_telegram("🚦 Démarrage de run_bot()...")
    
    lock_file = os.path.join(BASE_DIR, "bot.lock")

    if os.path.exists(lock_file):
        if is_another_bot_running(lock_file):
            logging.warning("⚠️ Une autre instance du bot est déjà en cours (process détecté). Abandon.")
            send_telegram("⚠️ Lancement annulé : une autre instance du bot est déjà en cours (process détecté).")
            return
        else:
            try:
                os.remove(lock_file)
                logging.info("🟢 Fichier bot.lock orphelin supprimé automatiquement.")
            except Exception as e:
                logging.error(f"❌ Impossible de supprimer bot.lock : {e}")
                send_telegram(f"❌ Impossible de supprimer bot.lock : {e}")
                return

    if os.path.exists(lock_file):
        logging.warning("⚠️ Une autre instance du bot est déjà en cours. Abandon.")
        send_telegram("⚠️ Lancement annulé : une autre instance du bot est déjà en cours.")
        return

    with open(lock_file, "w") as f:
        f.write("locked")

    try:
        send_telegram("🤖 Bot est bien lancé monsieur ...")
        update_status("ACTIF - En cours d'exécution ...")

        logging.info("🔁 Lancement des threads de surveillance...")
        resilient_thread(monitor_position, stop_event)

        levier = get_leverage_from_file()
        if change_leverage(symbol, levier):
            logging.info(f"✅ Levier mis à jour avec succès : x{levier}")
            send_telegram(f"✅ Levier mis à jour avec succès : x{levier}")
        else:
            logging.warning(f"⚠️ Levier non mis à jour : x{levier}")
            send_telegram(f"⚠️ Levier non mis à jour : x{levier}")

        backoff_time = 5
        max_backoff = 60
        logging.info("🔄 Démarrage du bot de trading...")

        while not stop_event.is_set():
            try:
                if should_stop():
                    stop_event.set()
                    send_telegram("🛑 Fichier stop.txt détecté, arrêt du bot.")
                    update_status("ARRÊT - Fichier stop.txt détecté")
                    break

                time.sleep(5)

                if manual_close_requested() and state.position_open:
                    close_position()
                    reset_manual_close()
                    time.sleep(2)

                log_system_usage()
                gc.collect()
                time.sleep(10)
                backoff_time = 5

            except Exception as e:
                send_telegram(f"❌ Erreur principale : {e}")
                update_status(f"ERREUR - {str(e)}")
                logging.error(f"⏳ Erreur rencontrée, nouvelle tentative dans {backoff_time}s... {e}")
                traceback.print_exc()
                gc.collect()
                time.sleep(backoff_time)
                backoff_time = min(max_backoff, backoff_time * 2)

        update_status("ARRÊT - Terminé proprement")

    finally:
        logging.info("🔒 Arrêt du bot, suppression du fichier de verrouillage...")
        if os.path.exists(lock_file):
            os.remove(lock_file)

def launch_bot():
    global trailing_thread, tp_thread, threads

    try:
        if not change_leverage(symbol, default_leverage):
            send_telegram(f"❌ Bot arrêté : changement de levier échoué sur {symbol}")
            return

        run_bot()


        t = threading.Thread(target=monitor_position, args=(stop_event,))
        t.start()
        threads.append(t)

        trailing_thread = resilient_thread(auto_set_sl_tp, stop_event)
        tp_thread = resilient_thread(manual_close_watcher, stop_event)

        logging.info("🔄 Lancement du bot de trading...")
    except Exception as e:
        send_telegram(f"❌ Erreur critique lors du lancement du bot : {e}")
        logging.error(f"❌ Erreur critique lors du lancement du bot : {e}")
        traceback.print_exc()

def get_dynamic_leverage():
    try:
        lev_path = os.path.join(BASE_DIR, "leverage.txt")
        with open(lev_path, "r") as f:
            lev = int(f.read().strip())
            return lev
    except Exception:
        return default_leverage

def get_dynamic_quantity():
    try:
        qty_path = os.path.join(BASE_DIR, "quantity.txt")
        with open(qty_path, "r") as f:
            qty = float(f.read().strip())
            return qty
    except Exception:
        return default_quantity_usdt

def retry_order(order_fn, max_retries=3, delay=2):
    for attempt in range(max_retries):
        try:
            return order_fn()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                send_telegram(f"❌ Erreur lors de la pose d'un ordre (SL/TP) : {e}")
                logging.error(f"❌ Erreur lors de la pose d'un ordre (SL/TP) : {e}")

def resilient_thread(target_fn, *args):
    def wrapper():
        retries = 0
        while True:
            try:
                target_fn(*args)
                break
            except Exception as e:
                logging.error(f"Thread {target_fn.__name__} crashé : {e}, relance dans 5s")
                retries += 1
                if retries > 10:
                    send_telegram(f"❌ Trop d'erreurs sur {target_fn.__name__}, thread arrêté.")
                    break
                time.sleep(5)
    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return t

def stop_bot():
    logging.warning("🔴 Arrêt du bot demandé...")
    stop_event.set()
    for t in threads:
        if t.is_alive():
            t.join(timeout=5)
    logging.warning("🟢 Tous les threads arrêtés.")

    if trailing_thread and trailing_thread.is_alive():
        trailing_thread.join()
    if tp_thread and tp_thread.is_alive():
        tp_thread.join()

    stop_telegram_bot()
    logging.warning("🟢 Tous les composants ont été arrêtés proprement.")

if __name__ == "__main__":
    sync_windows_time()
    launch_bot()