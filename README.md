# Bot de Trading Crypto - EMA, SL/TP Dynamique & Telegram

## 🚀 Présentation

Ce projet est un **bot de trading automatisé** pour Binance Futures, conçu pour détecter les croisements d’indicateurs EMA, gérer dynamiquement le Stop Loss (SL) et le Take Profit (TP), et envoyer des alertes en temps réel via Telegram.  
Il intègre plusieurs stratégies et modules pour une gestion robuste et flexible des positions, avec une architecture modulaire et extensible.

---

## 🧩 Fonctionnalités principales

- **Détection des croisements EMA (EMA9/EMA20, EMA20/EMA50, etc.)**
- **Gestion dynamique du SL et TP** (trailing, ajustement selon le gain)
- **Surveillance des zones clés (supports/résistances)**
- **Envoi d’alertes Telegram** (croisement, zone touchée, volatilité, ouverture/fermeture de position)
- **Ouverture et fermeture automatique des positions**
- **Gestion du levier et de la quantité en temps réel**
- **Logs détaillés et suivi des erreurs**
- **Protection anti-spam configurable**
- **Surveillance multi-timeframe (EMA 3m, 5m, live, etc.)**
- **Gestion manuelle possible (fichier stop, fermeture manuelle, etc.)**

---

## 📦 Structure du projet

```
MES PROJETS/
│
├── Bot de trading/
│   ├── ema4.py                # Stratégie EMA9/EMA20 + zones + Telegram
│   ├── ema5.py                # Stratégie EMA20/EMA50 simple
│   ├── main.py                # Lancement global, gestion des threads
│   ├── core/
│   │   ├── bot.py             # Logique principale du bot, gestion des positions
│   │   ├── trade_executor.py  # Ouverture/fermeture de trade, SL/TP
│   │   ├── trailing.py        # Gestion dynamique du SL/TP
│   │   ├── telegram_controller.py # Intégration Telegram
│   │   ├── binance_client.py  # Connexion Binance
│   │   ├── config.py          # Paramètres globaux
│   │   ├── state.py           # État global du bot
│   │   ├── trading_utils.py   # Fonctions utilitaires trading
│   │   ├── position_utils.py  # Synchronisation des positions
│   │   ├── notifier.py        # Notifications diverses
│   ├── strategies/
│   │   ├── ema_cross.py       # Boucles EMA 5m
│   │   ├── ema_3m.py          # Boucles EMA 3m
│   │   ├── ema_tracker.py     # Suivi live EMA
│   ├── logs/
│   │   ├── errors.txt         # Log des erreurs
│   │   ├── signals_log.csv    # Log des signaux
│   ├── .env                   # Clés API Binance, Telegram, etc.
│   ├── README.md              # Ce fichier
```

---

## ⚙️ Installation

1. **Cloner le projet**
   ```bash
   git clone <url_du_repo>
   cd MES\ PROJETS/Bot\ de\ trading
   ```

2. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurer l’environnement**
   - Crée un fichier `.env` à la racine :
     ```
     BINANCE_API_KEY=xxx
     BINANCE_API_SECRET=xxx
     TELEGRAM_TOKEN=xxx
     TELEGRAM_CHAT_ID=xxx
     ```
   - Vérifie les paramètres dans `core/config.py` (levier, quantité, symbol, etc.)

4. **Lancer le bot**
   ```bash
   python main.py
   ```

---

## 🛠 Utilisation

- **Lancement automatique** : `main.py` gère le démarrage du bot, la surveillance EMA, et le contrôleur Telegram.
- **Gestion manuelle** :
  - Pour arrêter le bot : crée un fichier `stop.txt` à la racine.
  - Pour fermer une position manuellement : crée un fichier `manual_close_request.txt`.
- **Logs et suivi** :
  - Les logs sont enregistrés dans `bot.log` et `logs/errors.txt`.
  - Les signaux sont enregistrés dans `logs/signals_log.csv`.

---

## 📊 Stratégies EMA

- **ema4.py** : Stratégie avancée EMA9/EMA20, détection de zones, confirmation pullback, alertes Telegram.
- **ema5.py** : Stratégie simple EMA20/EMA50, détection croisement, alertes Telegram.
- **Multi-timeframe** : Possibilité de lancer plusieurs boucles EMA (3m, 5m, live) en parallèle.

---

## 🔔 Alertes Telegram

- **Croisement EMA détecté** (haussier/baissier)
- **Prix proche d’un support ou d’une résistance**
- **Signal confirmé (LONG/SHORT)**
- **Ouverture/fermeture de position**
- **Volatilité élevée**
- **Erreur ou problème détecté**

---

## 🛡 Sécurité & Robustesse

- **Gestion des exceptions et des erreurs réseau**
- **Vérification du solde et des permissions Binance**
- **Protection contre les ordres orphelins (SL/TP)**
- **Synchronisation de l’heure locale avec Binance**
- **Gestion du levier dynamique**
- **Surveillance de la RAM et du CPU**

---

## 📈 Personnalisation

- **Paramètres modifiables** dans `.env` et `core/config.py` (levier, quantité, symbol, SL/TP, etc.)
- **Ajout de nouvelles stratégies** dans le dossier `strategies/`
- **Modification des seuils EMA, zones, volatilité, etc.**

---

## 🧑‍💻 Contribution

Les contributions sont les bienvenues !  
N’hésite pas à ouvrir une issue ou une pull request pour proposer des améliorations, corriger des bugs ou ajouter des stratégies.

---

## ❓ FAQ

**Q : Comment changer le symbole tradé ?**  
R : Modifie la variable `SYMBOL` dans `.env` ou dans `core/config.py`.

**Q : Comment recevoir les alertes sur mon Telegram ?**  
R : Renseigne ton `TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID` dans `.env`.

**Q : Que faire si le bot ne lance pas d’ordre ?**  
R : Vérifie le solde, les permissions Futures, et les logs d’erreur.

**Q : Peut-on utiliser ce bot sur d’autres plateformes ?**  
R : Actuellement, il est optimisé pour Binance Futures. Adaptation possible.

---

## 📜 Licence

Ce projet est open-source, sous licence MIT.  
Utilisation à vos risques et périls, aucune garantie sur les performances ou la sécurité.

---

## 🏁 Remerciements

Merci à tous les contributeurs, testeurs et à la communauté Python/Binance/Telegram pour leur soutien et leurs outils.

---

**Bonne chance et bon trading !** 🚀📈# Titanium
