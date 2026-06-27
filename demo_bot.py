"""
v27 SUPREME - Manual Confirmation + Auto-Expiry + All Features
Human must approve within 5 minutes or setup expires
"""
import time
import subprocess
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import requests

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]
ENTRY_TF = mt5.TIMEFRAME_M15
TREND_TF = mt5.TIMEFRAME_H1
CANDLE_COUNT = 200
RISK_PERCENT = 0.02
MIN_RISK_USD = 3.00
MAX_LOT = 0.01
MAX_TRADES_PER_DAY = 5
CONFIRMATION_TIMEOUT = 300  # 5 minutes to approve

TELEGRAM_TOKEN = "8619211321:AAGLwU1U235C9UFHzcB7Oc7T6T5rSxqr-S4"
TELEGRAM_CHAT_ID = "6125308716"
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

SESSION = requests.Session()
SESSION.trust_env = False
alerted_blocks = {}
breaker_blocks = {}
daily_trades = {}
last_trade_date = None
backtest_results = []
pending_approval = {}  # Stores setups waiting for human approval
last_reminder = {}     # Tracks when reminder was sent

def send_alert(text):
    try:
        SESSION.post(TELEGRAM_URL, json={'chat_id': TELEGRAM_CHAT_ID, 'text': text}, timeout=10)
    except:
        pass

def check_pending_approvals():
    """Check for expired pending approvals and remind if needed"""
    global pending_approval, last_reminder
    now = datetime.now()
    expired = []
    
    for trade_id, approval in list(pending_approval.items()):
        elapsed = (now - approval['created']).total_seconds()
        
        # Remind after 2 minutes
        if elapsed > 120 and trade_id not in last_reminder:
            send_alert(f"⏰ REMINDER: Trade awaiting approval!\n\n{approval['alert_text']}\n\nReply /approve {trade_id} or this expires in 3 minutes!")
            last_reminder[trade_id] = now
        
        # Expire after 5 minutes
        if elapsed > CONFIRMATION_TIMEOUT:
            send_alert(f"❌ EXPIRED: Trade {trade_id}\n{approval['symbol']} {approval['direction']}\nSetup aged {int(elapsed/60)}min - too risky, skipped!")
            expired.append(trade_id)
    
    for trade_id in expired:
        del pending_approval[trade_id]
        if trade_id in last_reminder:
            del last_reminder[trade_id]

def check_telegram_commands():
    """Check if user sent /approve command via Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-5"
        r = SESSION.get(url, timeout=5)
        if r.status_code == 200:
            updates = r.json().get('result', [])
            for update in updates:
                if 'message' in update and 'text' in update['message']:
                    text = update['message']['text']
                    msg_time = datetime.fromtimestamp(update['message']['date'])
                    
                    if text.startswith('/approve'):
                        trade_id = text.replace('/approve', '').strip()
                        if trade_id in pending_approval:
                            approval = pending_approval[trade_id]
                            ticket, msg = execute_trade(
                                approval['symbol'], approval['entry'], 
                                approval['stop_loss'], approval['take_profit'],
                                approval['lot'], approval['confidence'],
                                approval['direction']
                            )
                            if ticket:
                                send_alert(f"✅ APPROVED & EXECUTED!\n{trade_id}\nTicket: {ticket}")
                            else:
                                send_alert(f"❌ Execution failed: {msg}")
                            del pending_approval[trade_id]
                            if trade_id in last_reminder:
                                del last_reminder[trade_id]
                            return True
                    elif text.startswith('/skip'):
                        trade_id = text.replace('/skip', '').strip()
                        if trade_id in pending_approval:
                            send_alert(f"⏭️ SKIPPED: {trade_id}\nUser declined this setup")
                            del pending_approval[trade_id]
                            if trade_id in last_reminder:
                                del last_reminder[trade_id]
                            return True
    except:
        pass
    return False

def can_trade_today():
    global daily_trades, last_trade_date
    today = datetime.now().strftime("%Y-%m-%d")
    if last_trade_date != today:
        daily_trades = {}
        last_trade_date = today
    return len(daily_trades) < MAX_TRADES_PER_DAY

def execute_trade(symbol, entry, stop_loss, take_profit, lot_size, ai_confidence, direction="SHORT"):
    if not can_trade_today():
        return None, "Daily limit reached"
    if lot_size > MAX_LOT:
        lot_size = MAX_LOT
    if ai_confidence == "LOW":
        return None, "AI confidence too low"
    
    if direction == "SHORT":
        order_type = mt5.ORDER_TYPE_SELL_STOP
    else:
        order_type = mt5.ORDER_TYPE_BUY_STOP
    
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": entry,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 10,
        "magic": 270001,
        "comment": f"v27_{direction}_DEMO",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        daily_trades[result.order] = symbol
        backtest_results.append({
            'time': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'symbol': symbol,
            'direction': direction,
            'entry': entry,
            'sl': stop_loss,
            'tp': take_profit,
            'lot': lot_size,
            'ticket': result.order,
            'approved': True
        })
        return result.order, "EXECUTED"
    else:
        return None, f"Failed: {result.comment}"

def calculate_lot_size(symbol, risk_usd, stop_loss, price):
    if symbol == "XAUUSD":
        sl_pips = abs(stop_loss - price)
        lot = risk_usd / (sl_pips * 100)
    else:
        sl_pips = abs(stop_loss - price) * 10000
        lot = risk_usd / (sl_pips * 10)
    lot = max(0.01, round(lot, 2))
    return min(lot, MAX_LOT)

def is_kill_zone():
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()
    if weekday >= 5:
        return False, "Weekend"
    if 7 <= hour < 10:
        return True, "London KZ"
    if 13 <= hour < 16:
        return True, "NY KZ"
    if 15 <= hour < 17:
        return True, "London Close"
    return False, "Outside KZ"

def ask_ollama(symbol, price, entry, stop_loss, risk, lot, patterns, market_state, trend_bias, direction):
    prompt = f"""Trading signal:
{symbol} | Direction: {direction} | Price: {price} | Entry: {entry}
SL: {stop_loss} | Risk: ${risk} | Lot: {lot}
1H Trend: {trend_bias} | Patterns: {patterns}

Reply:
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
    return info.balance if info else None

def get_live_price(symbol):
    tick = mt5.symbol_info_tick(symbol)
    return tick.bid if tick else None

def get_ohlc_data(symbol, timeframe):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, CANDLE_COUNT)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def get_trend_bias(symbol):
    df = get_ohlc_data(symbol, TREND_TF)
    if df is None or len(df) < 20:
        return "NEUTRAL"
    sma20 = df['close'].rolling(20).mean().iloc[-1]
    sma50 = df['close'].rolling(50).mean().iloc[-1] if len(df) >= 50 else sma20
    current = float(df['close'].iloc[-1])
    highs = df['high'].rolling(5).max()
    lows = df['low'].rolling(5).min()
    higher_high = highs.iloc[-1] > highs.iloc[-10] if len(highs) >= 10 else False
    lower_low = lows.iloc[-1] < lows.iloc[-10] if len(lows) >= 10 else False
    if current < sma20 and current < sma50 and lower_low:
        return "BEARISH"
    elif current > sma20 and current > sma50 and higher_high:
        return "BULLISH"
    else:
        return "NEUTRAL"

def calculate_volume_profile(df):
    if df is None or len(df) < 20:
        return None
    price_range = float(df['high'].max()) - float(df['low'].min())
    if price_range == 0:
        return None
    num_bins = 20
    bin_size = price_range / num_bins
    bins = {}
    for i in range(len(df)):
        price_low = float(df['low'].iloc[i])
        price_high = float(df['high'].iloc[i])
        volume = float(df['tick_volume'].iloc[i])
        for j in range(num_bins):
            bin_price = float(df['low'].min()) + (j * bin_size)
            if price_low <= bin_price <= price_high:
                bins[round(bin_price, 2)] = bins.get(round(bin_price, 2), 0) + volume
    if not bins:
        return None
    poc = max(bins, key=bins.get)
    total_volume = sum(bins.values())
    sorted_bins = sorted(bins.items(), key=lambda x: x[1], reverse=True)
    cumulative = 0
    value_area_high = None
    value_area_low = None
    for price, vol in sorted_bins:
        cumulative += vol
        if value_area_high is None:
            value_area_high = price
            value_area_low = price
        else:
            value_area_high = max(value_area_high, price)
            value_area_low = min(value_area_low, price)
        if cumulative >= total_volume * 0.70:
            break
    current_price = float(df['close'].iloc[-1])
    if value_area_high and value_area_low:
        va_range = value_area_high - value_area_low
        state = "BALANCE" if va_range < price_range * 0.3 else "IMBALANCE"
    else:
        state = "UNKNOWN"
    return {'poc': poc, 'value_area_high': value_area_high, 'value_area_low': value_area_low, 'state': state}

def find_swing_points(df):
    if df is None or len(df) < 6:
        return None, None
    swing_highs = []
    swing_lows = []
    for i in range(3, len(df) - 3):
        if (df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i-2] and
            df['high'].iloc[i] > df['high'].iloc[i-3] and df['high'].iloc[i] > df['high'].iloc[i+1] and 
            df['high'].iloc[i] > df['high'].iloc[i+2] and df['high'].iloc[i] > df['high'].iloc[i+3]):
            swing_highs.append({'price': float(df['high'].iloc[i]), 'index': i, 'time': df.index[i]})
        if (df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i-2] and
            df['low'].iloc[i] < df['low'].iloc[i-3] and df['low'].iloc[i] < df['low'].iloc[i+1] and 
            df['low'].iloc[i] < df['low'].iloc[i+2] and df['low'].iloc[i] < df['low'].iloc[i+3]):
            swing_lows.append({'price': float(df['low'].iloc[i]), 'index': i, 'time': df.index[i]})
    return swing_highs, swing_lows

def detect_breaker_blocks(df, swing_highs, swing_lows, symbol):
    global breaker_blocks
    if symbol not in breaker_blocks:
        breaker_blocks[symbol] = []
    current_price = float(df['close'].iloc[-1])
    new_breakers = []
    for sh in swing_highs[-5:]:
        if current_price > sh['price']:
            new_breakers.append({'level': sh['price'], 'type': 'BULLISH_BREAKER', 'entry': current_price, 'stop_loss': sh['price']})
    for sl in swing_lows[-5:]:
        if current_price < sl['price']:
            new_breakers.append({'level': sl['price'], 'type': 'BEARISH_BREAKER', 'entry': current_price, 'stop_loss': sl['price']})
    if new_breakers:
        breaker_blocks[symbol].extend(new_breakers)
        return new_breakers
    return None

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
    if not swing_lows or len(swing_lows) < 2:
        return None
    current_price = float(df['close'].iloc[-1])
    recent_low = swing_lows[-1]['price']
    if current_price < recent_low:
        return {'broken_level': recent_low, 'current_price': current_price, 'direction': 'SHORT'}
    return None

def detect_choch_long(df, swing_highs):
    if not swing_highs or len(swing_highs) < 2:
        return None
    current_price = float(df['close'].iloc[-1])
    recent_high = swing_highs[-1]['price']
    if current_price > recent_high:
        return {'broken_level': recent_high, 'current_price': current_price, 'direction': 'LONG'}
    return None

def find_order_block_short(df, swing_lows):
    if not swing_lows:
        return None
    broken_low_idx = swing_lows[-1]['index']
    for i in range(broken_low_idx - 1, max(broken_low_idx - 10, 0), -1):
        if df['close'].iloc[i] > df['open'].iloc[i]:
            return {'entry': float(df['low'].iloc[i]), 'stop_loss': float(df['high'].iloc[i])}
    return {'entry': float(df['low'].iloc[broken_low_idx]), 'stop_loss': float(df['high'].iloc[broken_low_idx])}

def find_order_block_long(df, swing_highs):
    if not swing_highs:
        return None
    broken_high_idx = swing_highs[-1]['index']
    for i in range(broken_high_idx - 1, max(broken_high_idx - 10, 0), -1):
        if df['close'].iloc[i] < df['open'].iloc[i]:
            return {'entry': float(df['high'].iloc[i]), 'stop_loss': float(df['low'].iloc[i])}
    return {'entry': float(df['high'].iloc[broken_high_idx]), 'stop_loss': float(df['low'].iloc[broken_high_idx])}

def run_backtest():
    global backtest_results
    if len(backtest_results) < 1:
        return None
    total_trades = len(backtest_results)
    summary = f"BACKTEST ({total_trades} orders)\n\n"
    for symbol in SYMBOLS:
        sym_trades = [t for t in backtest_results if t['symbol'] == symbol]
        if sym_trades:
            shorts = [t for t in sym_trades if t['direction'] == 'SHORT']
            longs = [t for t in sym_trades if t['direction'] == 'LONG']
            summary += f"{symbol}: {len(sym_trades)} ({len(shorts)}S/{len(longs)}L)\n"
    shorts = [t for t in backtest_results if t['direction'] == 'SHORT']
    longs = [t for t in backtest_results if t['direction'] == 'LONG']
    summary += f"\nShorts: {len(shorts)} | Longs: {len(longs)}"
    if total_trades < 10:
        summary += f"\n\nNeed {10 - total_trades} more trades for stats"
    return summary

def main():
    print("=" * 60)
    print("v27 SUPREME - MANUAL APPROVAL + AUTO-EXPIRY")
    print(f"Approval timeout: {CONFIRMATION_TIMEOUT}s | Max: {MAX_TRADES_PER_DAY}/day")
    print("=" * 60)
    
    if not mt5.initialize():
        return
    
    balance = get_demo_balance()
    for sym in SYMBOLS:
        mt5.symbol_select(sym, True)
    
    in_kz, session_name = is_kill_zone()
    kz_status = f"Active: {session_name}" if in_kz else f"Waiting... ({session_name})"
    
    send_alert(f"v27 MANUAL APPROVAL ONLINE\nPairs: {', '.join(SYMBOLS)}\nBalance: ${balance:.2f}\nMode: Manual Confirm (5min expiry)\nMax: {MAX_TRADES_PER_DAY}/day\nKill Zones: {kz_status}\n\nReply /approve ID or /skip ID\n$0 Real Money!")
    
    scan = 0
    while True:
        try:
            scan += 1
            
            # Check for expired approvals and user commands
            check_pending_approvals()
            check_telegram_commands()
            
            in_kz, session_name = is_kill_zone()
            
            for symbol in SYMBOLS:
                if not in_kz:
                    continue
                
                price = get_live_price(symbol)
                if price is None:
                    continue
                
                trend_bias = get_trend_bias(symbol)
                ohlc = get_ohlc_data(symbol, ENTRY_TF)
                if ohlc is None:
                    continue
                
                vp = calculate_volume_profile(ohlc)
                swing_highs, swing_lows = find_swing_points(ohlc)
                if not swing_highs or not swing_lows:
                    continue
                
                choch_short = detect_choch_short(ohlc, swing_lows)
                choch_long = detect_choch_long(ohlc, swing_highs)
                sweeps = detect_liquidity_sweep(ohlc, swing_highs, swing_lows)
                fvgs = detect_fvg(ohlc)
                breakers = detect_breaker_blocks(ohlc, swing_highs, swing_lows, symbol)
                
                # SHORT SETUP
                if trend_bias == "BEARISH" and (choch_short or sweeps or breakers):
                    patterns = [session_name, f"1H:{trend_bias}"]
                    if choch_short:
                        patterns.append("CHoCH")
                    if sweeps:
                        for s in sweeps:
                            patterns.append(f"SWEEP({s['type']})")
                    if fvgs:
                        patterns.append(f"FVG({fvgs[-1]['type']})")
                    if breakers:
                        patterns.append(f"BREAKER({breakers[0]['type']})")
                    if vp:
                        patterns.append(vp['state'])
                    
                    if breakers and breakers[0]['type'] == 'BEARISH_BREAKER':
                        entry = breakers[0]['entry']
                        stop_loss = breakers[0]['stop_loss']
                    else:
                        order_block = find_order_block_short(ohlc, swing_lows)
                        if order_block and order_block['entry'] > price:
                            entry = order_block['entry']
                            stop_loss = order_block['stop_loss']
                        else:
                            continue
                    direction = "SHORT"
                    
                # LONG SETUP
                elif trend_bias == "BULLISH" and (choch_long or sweeps or breakers):
                    patterns = [session_name, f"1H:{trend_bias}"]
                    if choch_long:
                        patterns.append("CHoCH")
                    if sweeps:
                        for s in sweeps:
                            patterns.append(f"SWEEP({s['type']})")
                    if fvgs:
                        patterns.append(f"FVG({fvgs[-1]['type']})")
                    if breakers:
                        patterns.append(f"BREAKER({breakers[0]['type']})")
                    if vp:
                        patterns.append(vp['state'])
                    
                    if breakers and breakers[0]['type'] == 'BULLISH_BREAKER':
                        entry = breakers[0]['entry']
                        stop_loss = breakers[0]['stop_loss']
                    else:
                        order_block = find_order_block_long(ohlc, swing_highs)
                        if order_block and order_block['entry'] < price:
                            entry = order_block['entry']
                            stop_loss = order_block['stop_loss']
                        else:
                            continue
                    direction = "LONG"
                else:
                    continue
                
                block_id = f"{symbol}_{direction}_{entry:.4f}"
                if symbol in alerted_blocks and alerted_blocks[symbol] == block_id:
                    continue
                
                alerted_blocks[symbol] = block_id
                
                risk_usd = round(abs(stop_loss - price), 4)
                if risk_usd <= 0:
                    continue
                
                tp = round(entry + (risk_usd * 2.17), 4) if direction == "LONG" else round(entry - (risk_usd * 2.17), 4)
                balance = get_demo_balance()
                max_risk = max(MIN_RISK_USD, round(balance * RISK_PERCENT, 2)) if balance else MIN_RISK_USD
                
                actual_risk = min(risk_usd, max_risk)
                lot = calculate_lot_size(symbol, actual_risk, stop_loss, price)
                
                demo_status = "VALID" if risk_usd <= max_risk else "BLOCKED"
                real_status = "VALID" if risk_usd <= MIN_RISK_USD else "BLOCKED"
                
                pattern_str = " + ".join(patterns)
                market_state = vp['state'] if vp else "UNKNOWN"
                
                ai_response = ask_ollama(symbol, price, entry, stop_loss, risk_usd, lot, pattern_str, market_state, trend_bias, direction)
                
                ai_lines = ai_response.split('\n')
                confidence = "MEDIUM"
                reason = ""
                action = "TAKE"
                for line in ai_lines:
                    if line.startswith("CONFIDENCE:"):
                        confidence = line.split(":")[1].strip()
                    if line.startswith("REASON:"):
                        reason = line.split(":", 1)[1].strip()
                    if line.startswith("ACTION:"):
                        action = line.split(":")[1].strip()
                
                if direction == "LONG":
                    emoji = "🟢 LONG"
                else:
                    emoji = "🔴 SHORT"
                
                if "CHoCH" in pattern_str and "SWEEP" in pattern_str and "FVG" in pattern_str:
                    signal = "ELITE"
                elif "BREAKER" in pattern_str:
                    signal = "BREAKER"
                elif "CHoCH" in pattern_str:
                    signal = "PREMIUM"
                else:
                    signal = "STANDARD"
                
                # Generate unique trade ID
                trade_id = f"{symbol[:3]}{datetime.now().strftime('%H%M%S')}"
                
                vp_info = ""
                if vp:
                    vp_info = f"\nPOC: {vp['poc']}\nValue Area: {vp['value_area_low']} - {vp['value_area_high']}\nState: {vp['state']}"
                
                alert_text = f"{emoji} {signal} [{session_name}]\n\nID: {trade_id}\n{symbol}\n1H Trend: {trend_bias}\nPrice: {price}\nEntry: {entry}\nStop Loss: {stop_loss}\nTake Profit: {tp}\nRisk: ${risk_usd}\nLot Size: {lot}{vp_info}\n\nPatterns: {pattern_str}\nAI: {confidence}\n{reason}\n\n⏰ Expires in 5 minutes!\nReply /approve {trade_id} or /skip {trade_id}"
                
                # Store for approval (NOT auto-executed)
                pending_approval[trade_id] = {
                    'symbol': symbol,
                    'entry': entry,
                    'stop_loss': stop_loss,
                    'take_profit': tp,
                    'lot': lot,
                    'confidence': confidence,
                    'direction': direction,
                    'created': datetime.now(),
                    'alert_text': alert_text
                }
                
                send_alert(alert_text)
                print(f"#{scan} | {symbol} | {direction} | {signal} | AWAITING APPROVAL: {trade_id}")
            
            if scan % 10 == 0:
                prices = []
                for sym in SYMBOLS:
                    p = get_live_price(sym)
                    if p:
                        trends = get_trend_bias(sym)
                        if sym == "XAUUSD":
                            prices.append(f"{sym}: {p:.2f} ({trends})")
                        else:
                            prices.append(f"{sym}: {p:.5f} ({trends})")
                kz_msg = f"Kill Zone: {session_name}" if in_kz else f"Outside KZ ({session_name})"
                pending_count = len(pending_approval)
                bt = run_backtest() if scan % 30 == 0 else ""
                msg = f"Scan #{scan}\n\n{chr(10).join(prices)}\n\n{kz_msg}\nPending: {pending_count}"
                if bt:
                    msg += f"\n\n{bt}"
                send_alert(msg)
            
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