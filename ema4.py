import time
import logging
import pandas as pd
from ta.trend import EMAIndicator
from dotenv import load_dotenv
import os
from binance.client import Client
from core.telegram_controller import send_telegram
import datetime

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

def get_klines_securise(*args, **kwargs):
    for _ in range(3):
        try:
            return get_klines(*args, **kwargs)
        except Exception as e:
            logging.warning("Erreur API Binance, nouvelle tentative...")
            time.sleep(2)
    raise Exception("Échec récupération des données Binance.")

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
        return "🚨📉 Croisement haussier détecté! \nEMA20 a croisé au-dessus de EMA50."

    # Croisement baissier : EMA20 passe en dessous de EMA50
    if prev_ema20 > prev_ema50 and curr_ema20 < curr_ema50:
        return "🚨📉 Croisement baissier détecté! \nEMA20 a croisé en dessous de EMA50."

    return None

def detect_support_resistance(df, window=20):
    # Support = plus bas récent, résistance = plus haut récent
    support = df["low"].astype(float).rolling(window).min().iloc[-1]
    resistance = df["high"].astype(float).rolling(window).max().iloc[-1]
    return support, resistance

def detect_tendance(prix_ema9, prix_ema20):
    if prix_ema9[-1] > prix_ema20[-1]:
        return "haussière"
    elif prix_ema9[-1] < prix_ema20[-1]:
        return "baissière"
    else:
        return "neutre"

def croisement_detecte(ema9, ema20):
    return (ema9[-2] < ema20[-2] and ema9[-1] > ema20[-1]) or \
           (ema9[-2] > ema20[-2] and ema9[-1] < ema20[-1])

def est_proche_zone(prix_actuel, zone, seuil=0.003):
    return abs(prix_actuel - zone) / prix_actuel < seuil

def block_orders_strategy(prix, ema9, ema20, supports, resistances):
    signal = None
    tendance = detect_tendance(ema9, ema20)
    croisement = croisement_detecte(ema9, ema20)
    prix_actuel = prix[-1]
    prix_cloture_precedente = prix[-2]

    if not croisement:
        return None

    if tendance == "haussière":
        for support in supports:
            if est_proche_zone(prix_actuel, support, seuil=0.002):
                if prix_cloture_precedente < support and prix_actuel > support:
                    signal = "long"
                elif prix_actuel > support and prix_cloture_precedente > support:
                    signal = "long"
                break
        for resistance in resistances:
            if est_proche_zone(prix_actuel, resistance, seuil=0.002):
                if prix_cloture_precedente < resistance and prix_actuel > resistance:
                    signal = "long"
                break
        if len(resistances) > 0 and prix_actuel > max(resistances) and ema9[-1] > ema20[-1]:
            if prix_cloture_precedente > max(resistances):
                signal = "long"

    elif tendance == "baissière":
        for support in supports:
            if est_proche_zone(prix_actuel, support, seuil=0.002):
                if prix_cloture_precedente > support and prix_actuel < support:
                    signal = "short"
                break
        for resistance in resistances:
            if est_proche_zone(prix_actuel, resistance, seuil=0.002):
                if prix_cloture_precedente > resistance and prix_actuel < resistance:
                    signal = "short"
                elif prix_actuel < resistance and prix_cloture_precedente < resistance:
                    signal = "short"
                break
    return signal

def regrouper_zones_proches(valeurs, tolerance=0.002):
    zones = []
    valeurs = sorted(set(valeurs))
    if not valeurs:
        return zones
    zone = [valeurs[0]]
    for val in valeurs[1:]:
        if abs(val - zone[-1]) / val <= tolerance:
            zone.append(val)
        else:
            zones.append(zone)
            zone = [val]
    zones.append(zone)
    return zones

def detect_supports_resistances_multi(df, window=40, max_points=3, tolerance=0.002):
    highs = df["high"].astype(float).iloc[-window:]
    lows = df["low"].astype(float).iloc[-window:]

    resistances_pot = highs[highs == highs.rolling(5, center=True).max()]
    supports_pot = lows[lows == lows.rolling(5, center=True).min()]

    resistances_groupées = regrouper_zones_proches(resistances_pot.dropna().tolist(), tolerance)
    supports_groupés = regrouper_zones_proches(supports_pot.dropna().tolist(), tolerance)

    prix_actuel = df["close"].iloc[-1]

    resistances_finales = sorted(
        [sum(zone) / len(zone) for zone in resistances_groupées],
        key=lambda x: abs(x - prix_actuel)
    )[:max_points]

    supports_finales = sorted(
        [sum(zone) / len(zone) for zone in supports_groupés],
        key=lambda x: abs(x - prix_actuel)
    )[:max_points]

    return supports_finales, resistances_finales

def calculer_window_dynamique(df):
    atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    volatilite = atr.iloc[-1]
    if volatilite > 1:
        return 50
    elif volatilite > 0.5:
        return 40
    else:
        return 30

def verifier_volatilite_et_notifier(df, seuil=1.0, flag=[False]):
    atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    volatilite = atr.iloc[-1]
    if volatilite > seuil and not flag[0]:
        send_telegram(f"🚨 Marché volatil détecté ! ATR actuel : {volatilite:.2f}")
        flag[0] = True
    elif volatilite <= seuil:
        flag[0] = False

prev_zones = {"supports": [], "resistances": []}

def zones_ont_change(supports, resistances):
    return supports != prev_zones["supports"] or resistances != prev_zones["resistances"]

def log_signal_csv(signal, prix, tendance, support, resistance):
    df_log = pd.DataFrame([{
        "timestamp": pd.Timestamp.now(),
        "signal": signal,
        "prix": prix,
        "tendance": tendance,
        "support": support,
        "resistance": resistance
    }])
    df_log.to_csv("signals_log.csv", mode="a", header=not os.path.exists("signals_log.csv"), index=False)

def confirmation_pullback(prix, zone, direction="haussière"):
    # Vérifie si le prix a cassé la zone puis est revenu dessus
    # direction = "haussière" pour support, "baissière" pour résistance
    if direction == "haussière":
        # Cassure du support puis retour (pullback)
        return prix[-2] < zone and prix[-1] > zone
    else:
        # Cassure de la résistance puis retour (pullback)
        return prix[-2] > zone and prix[-1] < zone

def main():
    send_telegram(f"🚦 Surveillance EMA4 lancée sur {SYMBOL} !")
    logging.info(f"Surveillance Block Orders EMA9/EMA20 sur {SYMBOL} toutes les 5 minutes...")

    last_signal = None

    while True:
        try:
            df = get_klines_securise(SYMBOL, INTERVAL, limit=100)
            verifier_volatilite_et_notifier(df)
            ema9 = EMAIndicator(close=df["close"], window=9).ema_indicator()
            ema20 = EMAIndicator(close=df["close"], window=20).ema_indicator()
            df["EMA9"] = ema9
            df["EMA20"] = ema20

            window = calculer_window_dynamique(df)
            supports, resistances = detect_supports_resistances_multi(df, window=window)
            prix = df["close"].values

            croisement = croisement_detecte(ema9.values, ema20.values)

            # Détection du type de croisement
            if ema9.values[-2] < ema20.values[-2] and ema9.values[-1] > ema20.values[-1]:
                type_croisement = "haussier"
            elif ema9.values[-2] > ema20.values[-2] and ema9.values[-1] < ema20.values[-1]:
                type_croisement = "baissier"
            else:
                type_croisement = "inconnu"

            # Détection de zone proche
            zone_interet = None
            for support in supports:
                if est_proche_zone(prix[-1], support, seuil=0.002):
                    zone_interet = f"support ({support:.4f})"
                    send_telegram(f"🟢 Prix proche du support {support:.4f} sur {SYMBOL}.")
            for resistance in resistances:
                if est_proche_zone(prix[-1], resistance, seuil=0.002):
                    zone_interet = f"résistance ({resistance:.4f})"
                    send_telegram(f"🔴 Prix proche de la résistance {resistance:.4f} sur {SYMBOL}.")

            signal = block_orders_strategy(prix, ema9.values, ema20.values, supports, resistances)

            # Bloc unique d'envoi de message (sans anti-spam)
            if croisement:
                if signal and signal != last_signal:
                    message = f"✅ Croisement EMA9/EMA20 {type_croisement} \navec signal {signal.upper()} confirmé"
                    if zone_interet:
                        message += f" près de la {zone_interet}"
                    else:
                        message += " loin de toute zone"
                    send_telegram(f"🚀 {message} sur {SYMBOL}.")
                    log_signal_csv(signal, prix[-1], detect_tendance(ema9.values, ema20.values), supports[0] if supports else None, resistances[0] if resistances else None)
                    last_signal = signal
                else:
                    if zone_interet:
                        send_telegram(f"🔄 Croisement EMA9/EMA20 {type_croisement} détecté \nprès de la {zone_interet}, mais pas de signal \nconfirmé sur {SYMBOL}.")
                    else:
                        send_telegram(f"🔄 Croisement EMA9/EMA20 {type_croisement} détecté \nloin de toute zone, pas de signal confirmé sur {SYMBOL}.")

            time.sleep(300)
        except Exception as e:
            logging.error(f"Erreur: {e}")
            send_telegram(f"⚠️ Erreur durant la surveillance : {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()