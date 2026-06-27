"""
MT5 Strategy Backtester v6 - XAUUSD + USDJPY + AUDUSD
Gold: 5M/NY/3:1/Sweeps | Forex: 15M/London+NY/2.17:1/CHoCH
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

SYMBOLS = ["XAUUSD", "USDJPY", "AUDUSD"]
START_DATE = datetime.now() - timedelta(days=90)
SPREAD_COST = {"XAUUSD": 0.30, "USDJPY": 0.020, "AUDUSD": 0.00020}

def get_pip_value(symbol):
    if symbol == "XAUUSD":
        return 100.0
    elif symbol == "USDJPY":
        return 1000.0
    else:
        return 100000.0

def get_settings(symbol):
    if symbol == "XAUUSD":
        return {'timeframe': mt5.TIMEFRAME_M5, 'min_bars': 8, 'max_daily': 4,
                'max_dist': 15.0, 'rr_ratio': 3.0, 'allow_sweeps': True, 'ny_only': True}
    else:
        return {'timeframe': mt5.TIMEFRAME_M15, 'min_bars': 15, 'max_daily': 3,
                'max_dist': 0.002, 'rr_ratio': 2.17, 'allow_sweeps': False, 'ny_only': False}

def get_historical_data(symbol, timeframe):
    rates = mt5.copy_rates_from(symbol, timeframe, START_DATE, 15000)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def find_swing_points(df):
    if df is None or len(df) < 6:
        return [], []
    swing_highs = []
    swing_lows = []
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

def get_trend_bias(df):
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

def detect_choch_short(df, swing_lows):
    if len(swing_lows) < 2:
        return False
    return float(df['close'].iloc[-1]) < swing_lows[-1]['price']

def detect_choch_long(df, swing_highs):
    if len(swing_highs) < 2:
        return False
    return float(df['close'].iloc[-1]) > swing_highs[-1]['price']

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

def simulate_trade(df, entry_idx, entry_price, stop_loss, direction, symbol, rr_ratio):
    tp_distance = abs(stop_loss - entry_price) * rr_ratio
    tp = entry_price - tp_distance if direction == "SHORT" else entry_price + tp_distance
    pip_val = get_pip_value(symbol)
    spread = SPREAD_COST.get(symbol, 0)
    filled = False
    
    for i in range(entry_idx + 1, len(df)):
        high = float(df['high'].iloc[i])
        low = float(df['low'].iloc[i])
        
        if not filled:
            if direction == "SHORT" and high >= entry_price:
                filled = True
            elif direction == "LONG" and low <= entry_price:
                filled = True
            else:
                continue
        
        if direction == "SHORT":
            if low <= tp:
                profit = (tp_distance * pip_val * 0.01) - spread
                return "WIN", round(profit, 2)
            if high >= stop_loss:
                loss = (stop_loss - entry_price) * pip_val * 0.01 + spread
                return "LOSS", round(-loss, 2)
        else:
            if high >= tp:
                profit = (tp_distance * pip_val * 0.01) - spread
                return "WIN", round(profit, 2)
            if low <= stop_loss:
                loss = (entry_price - stop_loss) * pip_val * 0.01 + spread
                return "LOSS", round(-loss, 2)
    
    return ("FILLED_OPEN", 0) if filled else ("UNFILLED", 0)

def backtest_symbol(symbol):
    settings = get_settings(symbol)
    tf = settings['timeframe']
    min_bars = settings['min_bars']
    max_daily = settings['max_daily']
    max_dist = settings['max_dist']
    rr = settings['rr_ratio']
    ny_only = settings['ny_only']
    allow_sweeps = settings['allow_sweeps']
    
    tf_label = "5M" if tf == mt5.TIMEFRAME_M5 else "15M"
    print(f"\nBacktesting {symbol} ({tf_label}, RR:{rr}, Sweeps:{allow_sweeps})...")
    
    df = get_historical_data(symbol, tf)
    if df is None or len(df) < 200:
        print(f"  Not enough data")
        return []
    
    trades = []
    last_trade_idx = 0
    daily_count = {}
    active_until = 0
    window = 200
    unfilled = 0
    
    step = 3 if symbol == "XAUUSD" else 5
    
    for end_idx in range(window, len(df) - 1, step):
        if end_idx - last_trade_idx < min_bars:
            continue
        if end_idx < active_until:
            continue
        
        trade_date = df.index[end_idx].strftime("%Y-%m-%d")
        if daily_count.get(trade_date, 0) >= max_daily:
            continue
        
        segment = df.iloc[end_idx - window:end_idx]
        trend = get_trend_bias(segment)
        if trend == "NEUTRAL":
            continue
        
        swing_highs, swing_lows = find_swing_points(segment)
        if not swing_highs or not swing_lows:
            continue
        
        trade_hour = df.index[end_idx].hour
        if ny_only:
            in_kz = (13 <= trade_hour < 17)
        else:
            in_kz = (7 <= trade_hour < 10) or (13 <= trade_hour < 17)
        if not in_kz:
            continue
        
        choch_short = detect_choch_short(segment, swing_lows)
        choch_long = detect_choch_long(segment, swing_highs)
        has_sweep = detect_liquidity_sweep(segment, swing_highs, swing_lows) is not None
        
        short_ok = choch_short or (allow_sweeps and has_sweep)
        long_ok = choch_long or (allow_sweeps and has_sweep)
        
        entry = stop_loss = None
        direction = None
        
        if trend == "BEARISH" and short_ok:
            ob = find_order_block_short(segment, swing_lows)
            if ob:
                entry, stop_loss = ob
                current = float(segment['close'].iloc[-1])
                dist_check = max_dist if symbol == "XAUUSD" else current * max_dist
                if entry > current and (entry - current) < dist_check:
                    direction = "SHORT"
        
        elif trend == "BULLISH" and long_ok:
            ob = find_order_block_long(segment, swing_highs)
            if ob:
                entry, stop_loss = ob
                current = float(segment['close'].iloc[-1])
                dist_check = max_dist if symbol == "XAUUSD" else current * max_dist
                if entry < current and (current - entry) < dist_check:
                    direction = "LONG"
        
        if direction is None:
            continue
        
        result, profit = simulate_trade(df, end_idx, entry, stop_loss, direction, symbol, rr)
        
        if result == "UNFILLED":
            unfilled += 1
            continue
        
        trades.append({
            'time': df.index[end_idx], 'symbol': symbol, 'direction': direction,
            'entry': round(entry, 5), 'stop_loss': round(stop_loss, 5),
            'result': result, 'profit': profit
        })
        last_trade_idx = end_idx
        daily_count[trade_date] = daily_count.get(trade_date, 0) + 1
        active_until = end_idx + 30
    
    if trades:
        wins = [t for t in trades if t['result'] == 'WIN']
        losses = [t for t in trades if t['result'] == 'LOSS']
        opens = [t for t in trades if t['result'] == 'FILLED_OPEN']
        total_profit = sum(t['profit'] for t in wins) if wins else 0.0
        total_loss = abs(sum(t['profit'] for t in losses)) if losses else 0.0
        resolved = len(wins) + len(losses)
        
        wr = round(len(wins) / resolved * 100, 1) if resolved > 0 else 0.0
        pf = round(total_profit / total_loss, 2) if total_loss > 0 else (99.9 if total_profit > 0 else 0.0)
        net_pl = total_profit - total_loss
        
        print(f"  Filled: {len(trades)} | Wins: {len(wins)} | Losses: {len(losses)} | Open: {len(opens)} | Unfilled: {unfilled}")
        print(f"  Win Rate: {wr}% | PF: {pf} | P&L: ${net_pl:.2f}")
    else:
        print(f"  No filled trades (Unfilled: {unfilled})")
    
    return trades

def main():
    print("=" * 60)
    print("v6 BACKTESTER - XAUUSD + USDJPY + AUDUSD")
    print(f"Period: {START_DATE.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}")
    print("XAUUSD: 5M/NY/3:1/Sweeps | Forex: 15M/All/2.17:1/CHoCH")
    print("=" * 60)
    
    if not mt5.initialize():
        print("MT5 not connected!")
        return
    
    all_trades = []
    for symbol in SYMBOLS:
        trades = backtest_symbol(symbol)
        all_trades.extend(trades)
    
    if all_trades:
        wins = [t for t in all_trades if t['result'] == 'WIN']
        losses = [t for t in all_trades if t['result'] == 'LOSS']
        total_profit = sum(t['profit'] for t in wins) if wins else 0.0
        total_loss = abs(sum(t['profit'] for t in losses)) if losses else 0.0
        resolved = len(wins) + len(losses)
        
        wr = round(len(wins) / resolved * 100, 1) if resolved > 0 else 0.0
        pf = round(total_profit / total_loss, 2) if total_loss > 0 else (99.9 if total_profit > 0 else 0.0)
        net_pl = total_profit - total_loss
        
        print("\n" + "=" * 60)
        print("OVERALL RESULTS")
        print("=" * 60)
        print(f"Total Filled: {len(all_trades)} | Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"Win Rate: {wr}% | Profit Factor: {pf}")
        print(f"Net Profit: ${net_pl:.2f}")
        
        print("\nPER-SYMBOL:")
        for sym in SYMBOLS:
            st = [t for t in all_trades if t['symbol'] == sym]
            if st:
                sw = len([t for t in st if t['result'] == 'WIN'])
                sl = len([t for t in st if t['result'] == 'LOSS'])
                sp = sum(t['profit'] for t in st)
                print(f"  {sym}: {len(st)} trades (W:{sw} L:{sl}) | ${sp:.2f}")
        
        df_results = pd.DataFrame(all_trades)
        df_results.to_csv("backtest_new_pairs.csv", index=False)
        print(f"\nSaved to backtest_new_pairs.csv")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
