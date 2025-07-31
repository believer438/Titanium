"""
Module : position_utils.py
But : Fournir une fonction pour synchroniser la position actuelle sur Binance
      avec l'état local du bot (state).
"""

from core.state import state
from core.binance_client import check_position_open
from core.config import symbol
from core.telegram_controller import send_telegram
from threading import Lock
import traceback
import logging

# Configuration du logging
logging.basicConfig(
    filename='bot.log',
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Lock pour éviter les conflits d'accès concurrentiels
position_lock = Lock()

def sync_position():
    """
    Synchronise l'état local avec la position réelle sur Binance.
    Met à jour state.position_open en fonction de l'info Binance.
    Gère les erreurs réseau/API.
    """
    try:
        with position_lock:
            pos_open = check_position_open(symbol=symbol)
            state.position_open = pos_open
    except Exception as e:
        logging.error(f"Erreur : {e}", exc_info=True)
        send_telegram(f"Erreur : {e}")
