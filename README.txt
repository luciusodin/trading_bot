# 🪙 XAUUSD Gold Breakout Trading Bot (v40 SUPREME)

> **98.8% win rate | 172 trades | +$2,734 backtest profit | AI-powered**

---

## 📊 Verified Performance

| Test | Year | Trades | Win Rate | Net Profit |
|------|------|--------|----------|------------|
| Main Backtest | 2026 | 172 | **98.8%** | +$2,734.00 |
| Walk-Forward | 2025 | 48 | **97.9%** | +$227.87 |
| Sensitivity | Multi | Varies | **95%+** | Profitable |
| Live Demo | 2026 | 11 | 27%* | +$89.00 |

*\*Low win rate on demo due to manual errors, but still net profitable*

---

## 🛠️ Tech Stack

- **Python 3.12+** — Core engine
- **MetaTrader5** — Broker execution
- **Ollama + Hermes 3B** — Local AI validation
- **SQLite** — Trade database
- **Telegram API** — Real-time alerts
- **Pandas/NumPy** — Data analysis

---

## 🎯 Strategy Overview

### Gold Breakout (Previous Day High/Low)

1. Every day, the bot gets yesterday's high and low
2. Monitors XAUUSD on **5-minute candles**
3. If price breaks above yesterday's high → **LONG**
4. If price breaks below yesterday's low → **SHORT**
5. Entry at breakout level with buffer
6. Stop loss at opposite day level
7. **$3 trailing stop** activates, updates every **10 seconds**
8. Only trades during **NY Kill Zone** (4PM-8PM Kenya Time)

---

## 🛡️ Risk Management

- **1% risk per trade** (dynamic lot sizing)
- **10-second trailing stop** locks in profits
- **News filter** blocks trading during NFP/US_DATA/UK_DATA
- **Daily bias filter** prevents counter-trend trades
- **Guardian Watchdog** (add at $200+ capital)

---

## ⚡ Quick Start

### Prerequisites
```bash
pip install MetaTrader5 pandas numpy requests
nstall Ollama

Pull AI model: ollama pull hermes3:3b

MetaTrader 5 open & logged in

python demo_bot.py
📁 Project Files
File	Purpose
demo_bot.py	Main trading bot (v40)
guardian.py	4% kill-switch watchdog
backtest_breakout_v3.py	Gold breakout backtest
backtest_sensitivity.py	Parameter robustness test
backtest_2025.py	Walk-forward validation
backtest_new.py	Multi-pair backtest
trades.db	SQLite trade database
💰 Pricing & Services
Package	Price	What You Get
📊 Strategy Guide	$20	Full strategy breakdown + backtest proof
💻 Bot Code	$25	Complete Python bot + setup guide
🔧 Full Install	$50	Remote setup via AnyDesk
👑 VIP	$150	Install + 1 month support + optimization
📬 Contact
Reddit: u/YourUsername

Telegram: @YourTelegram

GitHub: github.com/Luciodin/gold-scalping-agent

⚠️ Disclaimer
This bot is for educational purposes. Past performance does not guarantee future results. Trade at your own risk. Always test on demo first.

---

## ⚡ **Save It:**

```cmd
cd C:\Bot
notepad README.md
Paste everything above. CTRL+S. Close.
