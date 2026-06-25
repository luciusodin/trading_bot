"""
XAUUSD SUPREME Trading Bot - Shareable Version
=============================================
SETUP:
1. pip install MetaTrader5 pandas numpy requests
2. Install Ollama: https://ollama.com
3. ollama pull hermes3:3b
4. Create Telegram bot via @BotFather
5. Replace YOUR_TELEGRAM_TOKEN and YOUR_CHAT_ID below
6. Open MT5, login to demo/real account
7. python supreme_bot.py

STRATEGY:
- XAUUSD: 5M TF, NY Kill Zone, 3:1 RR, CHoCH + Sweeps
- Forex: 15M TF, London+NY KZ, 2.17:1 RR, CHoCH
- AI validation via local Hermes 3B (private, free)
- Manual execution (you place trades on MT5)
"""
import time
import subprocess
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import requests

# ============================================
# CONFIGURATION - CHANGE THESE!
# ============================================
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
SYMBOLS = ["XAUUSD", "USDJPY", "AUDUSD"]  # Change if desired
MAX_LOT = 0.01

# ============================================
# DO NOT CHANGE BELOW UNLESS YOU KNOW WHAT YOU'RE DOING
# ============================================
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
SESSION = requests.Session()
SESSION.trust_env = False
alerted_blocks = {}

def send_alert(text):
    try:
        SESSION.post(TELEGRAM_URL, json={'chat_id': TELEGRAM_CHAT_ID, 'text': text}, timeout=10)
    except:
        pass

def get_settings(symbol):
    if symbol == "XAUUSD":
        return {'entry_tf': mt5.TIMEFRAME_M5, 'trend_tf': mt5.TIMEFRAME_H1, 'macro_tf': mt5.TIMEFRAME_H4,
                'max_dist': 15.0, 'rr_ratio': 3.0, 'allow_sweeps': True, 'ny_only': True}
    else:
        return {'entry_tf': mt5.TIMEFRAME_M15, 'trend_tf': mt5.TIMEFRAME_H1, 'macro_tf': mt5.TIMEFRAME_H4,
                'max_dist': 0.002, 'rr_ratio': 2.17, 'allow_sweeps': False, 'ny_only': False}

def is_kill_zone(ny_only=False):
    now = datetime.now(datetime.UTC)
    hour = now.hour
    weekday = now.weekday()
    if weekday >= 5:
        return False, "Weekend"
    if ny_only:
        if 13 <= hour < 17:
            return True, "NY KZ"
        return False, "Outside KZ"
    if 7 <= hour < 10:
        return True, "London KZ"
    if 13 <= hour < 16:
        return True, "NY KZ"
    if 15 <= hour < 17:
        return True, "London Close"
    return False, "Outside KZ"

def ask_ollama(symbol, price, entry, stop_loss, risk_label, patterns, trend_bias, direction, orderflow, macro):
    prompt = f"""Trading signal:
{symbol} | Direction: {direction} | Price: {price} | Entry: {entry}
SL: {stop_loss} | Risk: {risk_label}
1H: {trend_bias} | 4H: {macro} | OF: {orderflow}
Patterns: {patterns}

Reply exactly:
CONFIDENCE: HIGH/MEDIUM/LOW
REASON: one sentence
ACTION: TAKE/WAIT/SKIP"""
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(['ollama', 'run', 'hermes3:3b', prompt], capture_output=True, text=True, timeout=30, startupinfo=startupinfo)
        return result.stdout.strip()
    except:
        return "CONFIDENCE: MEDIUM\nREASON: AI unavailable\nACTION: TAKE"

def get_demo_balance():
    info = mt5.account_info()
    return info.balance if info else 0

def get_live_price(symbol):
    tick = mt5.symbol_info_tick(symbol)
    return tick.bid if tick else None

def get_ohlc_data(symbol, timeframe):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 200)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def get_trend_bias(symbol, timeframe):
    df = get_ohlc_data(symbol, timeframe)
    if df is None or len(df) < 20:
        return "NEUTRAL"
    sma20 = df['close'].rolling(20).mean().iloc[-1]
    sma50 = df['close'].rolling(50).mean().iloc[-1] if len(df) >= 50 else sma20
    current = float(df['close'].iloc[-1])
    if current < sma20 and current < sma50:
        return "BEARISH"
    elif current > sma20 and current > sma50:
        return "BULLISH"
    return "NEUTRAL"

def find_swing_points(df):
    if df is None or len(df) < 6:
        return None, None
    swing_highs, swing_lows = [], []
    for i in range(3, len(df) - 3):
        if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i-2] and
            df['high'].iloc[i] > df['high'].iloc[i-3] and df['high'].iloc[i] > df['high'].iloc[i+1] and 
            df['high'].iloc[i] > df['high'].iloc[i+2] and df['high'].iloc[i] > df['high'].iloc[i+3]):
            swing_highs.append({'price': float(df['high'].iloc[i]), 'index': i})
        if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i-2] and
            df['low'].iloc[i] < df['low'].iloc[i-3] and df['low'].iloc[i] < df['low'].iloc[i+1] and 
            df['low'].iloc[i] < df['low'].iloc[i+2] and df['low'].iloc[i] < df['low'].iloc[i+3]):
            swing_lows.append({'price': float(df['low'].iloc[i]), 'index': i})
    return swing_highs, swing_lows

def detect_liquidity_sweep(df, swing_highs, swing_lows):
    sweeps = []
    current_price = float(df['close'].iloc[-1])
    recent_low = float(df['low'].iloc[-3:].min())
    recent_high = float(df['high'].iloc[-3:].max())
    for sl in swing_lows[-3:]:
        if recent_low < sl['price'] and current_price > sl['price']:
            sweeps.append({'type': 'LOW_SWEEP', 'level': sl['price']})
    for sh in swing_highs[-3:]:
        if recent_high > sh['price'] and current_price < sh['price']:
            sweeps.append({'type': 'HIGH_SWEEP', 'level': sh['price']})
    return sweeps if sweeps else None

def detect_fvg(df):
    fvgs = []
    for i in range(2, len(df) - 1):
        if df['low'].iloc[i] > df['high'].iloc[i-1]:
            fvgs.append({'type': 'BEARISH', 'top': float(df['low'].iloc[i]), 'bottom': float(df['high'].iloc[i-1])})
        elif df['high'].iloc[i] < df['low'].iloc[i-1]:
            fvgs.append({'type': 'BULLISH', 'top': float(df['low'].iloc[i-1]), 'bottom': float(df['high'].iloc[i])})
    return fvgs[-5:] if fvgs else None

def detect_choch_short(df, swing_lows):
    if len(swing_lows) < 2:
        return False
    return float(df['close'].iloc[-1]) < swing_lows[-1]['price']

def detect_choch_long(df, swing_highs):
    if len(swing_highs) < 2:
        return False
    return float(df['close'].iloc[-1]) > swing_highs[-1]['price']

def find_order_block_short(df, swing_lows):
    if not swing_lows:
        return None
    idx = swing_lows[-1]['index']
    for i in range(idx - 1, max(idx - 10, 0), -1):
        if df['close'].iloc[i] > df['open'].iloc[i]:
            return float(df['low'].iloc[i]), float(df['high'].iloc[i])
    return float(df['low'].iloc[idx]), float(df['high'].iloc[idx])

def find_order_block_long(df, swing_highs):
    if not swing_highs:
        return None
    idx = swing_highs[-1]['index']
    for i in range(idx - 1, max(idx - 10, 0), -1):
        if df['close'].iloc[i] < df['open'].iloc[i]:
            return float(df['high'].iloc[i]), float(df['low'].iloc[i])
    return float(df['high'].iloc[idx]), float(df['low'].iloc[idx])

def get_order_type(direction, entry, price):
    if direction == "SHORT":
        return "SELL LIMIT" if entry > price else "SELL STOP"
    else:
        return "BUY LIMIT" if entry < price else "BUY STOP"

def get_risk_label(symbol, risk_usd):
    if symbol == "XAUUSD":
        return f"${risk_usd:.2f}"
    else:
        return f"{round(risk_usd * 10000, 1)} pips"

def get_order_flow_delta(symbol):
    try:
        now = datetime.now(datetime.UTC)
        ticks = mt5.copy_ticks_from(symbol, now - timedelta(minutes=2), 5000, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) < 100:
            return None
        df = pd.DataFrame(ticks)
        buy_vol = sell_vol = 0
        for i in range(1, len(df)):
            if df['bid'].iloc[i] > df['bid'].iloc[i-1]:
                buy_vol += df['volume'].iloc[i] if 'volume' in df.columns else 1
            elif df['bid'].iloc[i] < df['bid'].iloc[i-1]:
                sell_vol += df['volume'].iloc[i] if 'volume' in df.columns else 1
        total = buy_vol + sell_vol
        if total == 0:
            return None
        return {'delta': buy_vol - sell_vol, 'buy_pct': round(buy_vol/total*100,1), 'sell_pct': round(sell_vol/total*100,1)}
    except:
        return None

def main():
    print("=" * 60)
    print("XAUUSD SUPREME TRADING BOT")
    print("Gold: 5M/NY/3:1 | Forex: 15M/All/2.17:1")
    print("=" * 60)
    
    if not mt5.initialize():
        print("ERROR: MT5 not found! Is MetaTrader 5 open?")
        return
    
    balance = get_demo_balance()
    for sym in SYMBOLS:
        mt5.symbol_select(sym, True)
    
    send_alert(f"SUPREME BOT ONLINE\nPairs: {', '.join(SYMBOLS)}\nBalance: ${balance:.2f}\nGold: 5M/NY/3:1 | Forex: 15M/All/2.17:1\n$0 Real Money!")
    
    scan = 0
    while True:
        try:
            scan += 1
            for symbol in SYMBOLS:
                settings = get_settings(symbol)
                ny_only = settings['ny_only']
                allow_sweeps = settings['allow_sweeps']
                rr = settings['rr_ratio']
                max_dist = settings['max_dist']
                entry_tf = settings['entry_tf']
                trend_tf = settings['trend_tf']
                macro_tf = settings['macro_tf']
                
                in_kz, session_name = is_kill_zone(ny_only)
                if not in_kz:
                    continue
                
                price = get_live_price(symbol)
                if price is None:
                    continue
                
                trend_bias = get_trend_bias(symbol, trend_tf)
                macro_bias = get_trend_bias(symbol, macro_tf)
                ohlc = get_ohlc_data(symbol, entry_tf)
                if ohlc is None:
                    continue
                
                swing_highs, swing_lows = find_swing_points(ohlc)
                if not swing_highs or not swing_lows:
                    continue
                
                choch_short = detect_choch_short(ohlc, swing_lows)
                choch_long = detect_choch_long(ohlc, swing_highs)
                sweeps = detect_liquidity_sweep(ohlc, swing_highs, swing_lows)
                fvgs = detect_fvg(ohlc)
                orderflow = get_order_flow_delta(symbol)
                
                short_ok = choch_short or (allow_sweeps and sweeps)
                long_ok = choch_long or (allow_sweeps and sweeps)
                
                order_type = None
                
                if trend_bias == "BEARISH" and macro_bias in ["BEARISH", "NEUTRAL"] and short_ok:
                    patterns = [session_name, f"1H:{trend_bias}", f"4H:{macro_bias}"]
                    if choch_short: patterns.append("CHoCH")
                    if sweeps:
                        for s in sweeps: patterns.append(f"SWEEP({s['type']})")
                    if fvgs: patterns.append(f"FVG({fvgs[-1]['type']})")
                    
                    ob = find_order_block_short(ohlc, swing_lows)
                    if ob and ob[0] > price:
                        entry, stop_loss = ob
                        dist_check = max_dist if symbol == "XAUUSD" else price * max_dist
                        if (entry - price) < dist_check:
                            order_type = "SELL LIMIT"
                            direction = "SHORT"
                            emoji = "SHORT"
                        else:
                            continue
                    else:
                        continue
                    
                elif trend_bias == "BULLISH" and macro_bias in ["BULLISH", "NEUTRAL"] and long_ok:
                    patterns = [session_name, f"1H:{trend_bias}", f"4H:{macro_bias}"]
                    if choch_long: patterns.append("CHoCH")
                    if sweeps:
                        for s in sweeps: patterns.append(f"SWEEP({s['type']})")
                    if fvgs: patterns.append(f"FVG({fvgs[-1]['type']})")
                    
                    ob = find_order_block_long(ohlc, swing_highs)
                    if ob and ob[0] < price:
                        entry, stop_loss = ob
                        dist_check = max_dist if symbol == "XAUUSD" else price * max_dist
                        if (price - entry) < dist_check:
                            order_type = "BUY LIMIT"
                            direction = "LONG"
                            emoji = "LONG"
                        else:
                            continue
                    else:
                        continue
                else:
                    continue
                
                block_id = f"{symbol}_{direction}_{entry:.4f}"
                if symbol in alerted_blocks and alerted_blocks[symbol] == block_id:
                    continue
                alerted_blocks[symbol] = block_id
                
                risk_usd = round(abs(stop_loss - entry), 4)
                if risk_usd <= 0:
                    continue
                
                tp = round(entry + (risk_usd * rr), 4) if direction == "LONG" else round(entry - (risk_usd * rr), 4)
                lot = 0.01
                risk_label = get_risk_label(symbol, risk_usd)
                
                of_str = f"Buy:{orderflow['buy_pct']}% Sell:{orderflow['sell_pct']}%" if orderflow else "N/A"
                pattern_str = " + ".join(patterns)
                
                ai_response = ask_ollama(symbol, price, entry, stop_loss, risk_label, pattern_str, trend_bias, direction, of_str, macro_bias)
                
                confidence, reason, action = "MEDIUM", "", "TAKE"
                for line in ai_response.split('\n'):
                    line = line.strip()
                    if line.upper().startswith("CONFIDENCE:"):
                        confidence = line.split(":", 1)[1].strip()
                    elif line.upper().startswith("REASON:"):
                        reason = line.split(":", 1)[1].strip()
                    elif line.upper().startswith("ACTION:"):
                        action = line.split(":", 1)[1].strip()
                
                if choch_short or choch_long:
                    signal = "PREMIUM"
                elif sweeps:
                    signal = "SWEEP"
                else:
                    signal = "SIGNAL"
                
                if macro_bias == trend_bias:
                    signal = f"MTF_{signal}"
                
                tf_label = "5M" if symbol == "XAUUSD" else "15M"
                alert = f"{emoji} {signal} [{session_name}]\n\n{symbol} ({tf_label})\n1H: {trend_bias} | 4H: {macro_bias}\nPrice: {price}\nEntry: {entry}\nOrder: {order_type}\nSL: {stop_loss}\nTP: {tp}\nRisk: {risk_label}\nLot: {lot}\nRR: 1:{rr}\n\nPatterns: {pattern_str}\nAI: {confidence} ({action})\n{reason}\n\nPLACE MANUALLY ON MT5"
                
                send_alert(alert)
                print(f"#{scan} | {symbol} | {direction} | {signal}")
            
            if scan % 10 == 0:
                prices = []
                for sym in SYMBOLS:
                    p = get_live_price(sym)
                    if p:
                        s = get_settings(sym)
                        t = get_trend_bias(sym, s['trend_tf'])
                        tf = "5M" if sym == "XAUUSD" else "15M"
                        prices.append(f"{sym}({tf}): {p:.2f} ({t})" if sym == "XAUUSD" else f"{sym}({tf}): {p:.5f} ({t})")
                send_alert(f"Scan #{scan}\n\n{chr(10).join(prices)}")
            
            time.sleep(180)
            
        except KeyboardInterrupt:
            send_alert("Bot Stopped")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(30)
    
    mt5.shutdown()

if __name__ == "__main__":
    main()