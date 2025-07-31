import threading
import signal
import sys
import logging
import time
import gc
import psutil
from core.bot import launch_bot, stop_bot
from core.telegram_controller import start_bot, stop_telegram_bot
from strategies.ema_cross import start_ema_5m_loop, ema_live_watch_loop # ou autre chemin correct
from strategies.ema_3m import start_ema_3m_loop
from core.notifier import send_telegram
from strategies.ema_tracker import track_ema_live_crossing

logging.basicConfig(
    filename='bot.log',
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_system_usage():
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent()
    logging.warning(f"RAM utilisée : {mem.percent}% | CPU : {cpu}%")
    send_telegram(f"📊 Usage système - RAM : {mem.percent}% | CPU : {cpu}%")

def main():
    logging.info("🚀 Lancement du bot de trading et du contrôleur Telegram...")

    # Démarre le bot de trading dans un thread daemon
    bot_thread = threading.Thread(target=launch_bot, daemon=True)
    bot_thread.start()
    logging.info("✅ Bot de trading lancé.")
    
    # Lancer les boucles EMA dans des threads séparés
    ema_5m_thread = threading.Thread(target=start_ema_5m_loop, daemon=True)
    ema_3m_thread = threading.Thread(target=start_ema_3m_loop, daemon=True)
    ema_live_thread = threading.Thread(target=ema_live_watch_loop, daemon=True)

    ema_5m_thread.start()
    ema_3m_thread.start()
    ema_live_thread.start()

    threading.Thread(target=track_ema_live_crossing, daemon=True).start()

    # Fonction pour gérer l'arrêt propre sur Ctrl+C
    def signal_handler(sig, frame):
        logging.warning("🔴 Arrêt demandé. Fermeture en cours...")
        stop_bot()
        stop_telegram_bot()
        sys.exit(0)

    # Liaison du signal SIGINT (Ctrl+C) à la fonction d'arrêt
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Le bot Telegram tourne dans le thread principal
    start_bot()

    while True:
        try:
            # Ton code principal ici
            pass
        except Exception as e:
            logging.error(f"Erreur critique : {e}")
        gc.collect()
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            logging.error("RAM presque pleine !")
        log_system_usage()
        time.sleep(15)

if __name__ == "__main__":
    main()
