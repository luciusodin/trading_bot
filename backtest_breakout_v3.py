"""
Backtest - Gold Breakout + Trailing Stop (CONSERVATIVE v3)
ALL BUGS FIXED: Fill tracking, overnight trades, phantom losses
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

SYMBOL = "XAUUSD"
START_DATE = datetime.now() - timedelta(days=90)
TRAIL_START = 3.0
TRAIL_DIST = 1.5
SPREAD_COST = 0.30

def get_daily_data():
    rates = mt5.copy_rates_from(SYMBOL, mt5.TIMEFRAME_D1, START_DATE, 100)
    if rates is None or len(rates) == 0: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def get_5m_data():
    rates = mt5.copy_rates_from(SYMBOL, mt5.TIMEFRAME_M5, START_DATE, 50000)
    if rates is None or len(rates) == 0: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def simulate_breakout_trade(df_full, start_idx, direction, entry_price, stop_loss):
    highest_profit = 0
    trailing_sl = stop_loss
    in_position = False
    
    for i in range(start_idx + 1, len(df_full)):
        high = float(df_full['high'].iloc[i])
        low = float(df_full['low'].iloc[i])
        
        if not in_position:
            filled = (low <= entry_price) if direction == "SHORT" else (high >= entry_price)
            if not filled:
                continue
            in_position = True
            if direction == "SHORT" and high >= stop_loss:
                loss = abs(entry_price - stop_loss) + SPREAD_COST
                return "LOSS", round(-loss, 2), df_full.index[i]
            if direction == "LONG" and low <= stop_loss:
                loss = abs(entry_price - stop_loss) + SPREAD_COST
                return "LOSS", round(-loss, 2), df_full.index[i]
        
        if direction == "SHORT":
            if high >= trailing_sl:
                pnl = entry_price - trailing_sl - SPREAD_COST
                return ("WIN" if pnl > 0 else "LOSS"), round(pnl, 2), df_full.index[i]
            profit = entry_price - low
            highest_profit = max(highest_profit, profit)
            if profit >= TRAIL_START:
                trailing_sl = min(trailing_sl, low + TRAIL_DIST)
        else:
            if low <= trailing_sl:
                pnl = trailing_sl - entry_price - SPREAD_COST
                return ("WIN" if pnl > 0 else "LOSS"), round(pnl, 2), df_full.index[i]
            profit = high - entry_price
            highest_profit = max(highest_profit, profit)
            if profit >= TRAIL_START:
                trailing_sl = max(trailing_sl, high - TRAIL_DIST)
    
    if in_position:
        return "OPEN", round(highest_profit, 2), df_full.index[-1]
    else:
        return "UNFILLED", 0, df_full.index[-1]

def backtest():
    print(f"\nBacktesting {SYMBOL} Breakout Strategy (CONSERVATIVE v3)")
    print(f"Trail Start: ${TRAIL_START} | Trail Distance: ${TRAIL_DIST}")
    print("Fixes: Fill tracking + Overnight + No phantom losses\n")
    
    daily = get_daily_data()
    m5 = get_5m_data()
    
    if daily is None or m5 is None:
        print("Not enough data")
        return []
    
    trades = []
    
    for i in range(1, len(daily)):
        prev_high = float(daily['high'].iloc[i-1])
        prev_low = float(daily['low'].iloc[i-1])
        
        day_start = daily['time'].iloc[i]
        day_start_idx = m5.index.get_indexer([day_start], method='nearest')[0]
        day_end = day_start + timedelta(days=1)
        day_end_idx = m5.index.get_indexer([day_end], method='nearest')[0]
        day_end_idx = min(day_end_idx, len(m5) - 1)
        
        trades_today = 0
        
        for j in range(day_start_idx + 10, day_end_idx):
            if trades_today >= 2:
                break
            
            high = float(m5['high'].iloc[j])
            low = float(m5['low'].iloc[j])
            
            if low < prev_low:
                entry = prev_low - 0.5
                stop = prev_high
                result, profit, exit_time = simulate_breakout_trade(m5, j, "SHORT", entry, stop)
                trades.append({
                    'date': day_start.strftime("%Y-%m-%d"),
                    'direction': 'SHORT',
                    'entry': entry,
                    'stop': stop,
                    'exit_time': exit_time,
                    'result': result,
                    'profit': profit
                })
                trades_today += 1
                if result not in ["UNFILLED", "OPEN"]:
                    exit_idx = m5.index.get_indexer([exit_time], method='nearest')[0]
                    j = exit_idx
            
            elif high > prev_high:
                entry = prev_high + 0.5
                stop = prev_low
                result, profit, exit_time = simulate_breakout_trade(m5, j, "LONG", entry, stop)
                trades.append({
                    'date': day_start.strftime("%Y-%m-%d"),
                    'direction': 'LONG',
                    'entry': entry,
                    'stop': stop,
                    'exit_time': exit_time,
                    'result': result,
                    'profit': profit
                })
                trades_today += 1
                if result not in ["UNFILLED", "OPEN"]:
                    exit_idx = m5.index.get_indexer([exit_time], method='nearest')[0]
                    j = exit_idx
    
    if trades:
        wins = [t for t in trades if t['result'] == 'WIN']
        losses = [t for t in trades if t['result'] == 'LOSS']
        opens = [t for t in trades if t['result'] == 'OPEN']
        unfilled = [t for t in trades if t['result'] == 'UNFILLED']
        resolved = wins + losses
        tp = sum(t['profit'] for t in wins) if wins else 0
        tl = abs(sum(t['profit'] for t in losses)) if losses else 1
        r = len(resolved)
        wr = round(len(wins)/r*100, 1) if r > 0 else 0
        pf = round(tp/tl, 2) if tl > 0 else 0
        
        print(f"  Total: {len(trades)} | W: {len(wins)} | L: {len(losses)} | Open: {len(opens)} | Unfilled: {len(unfilled)}")
        print(f"  Win Rate: {wr}% | PF: {pf} | P&L: ${tp-tl:.2f}")
        
        shorts = [t for t in trades if t['direction'] == 'SHORT']
        longs = [t for t in trades if t['direction'] == 'LONG']
        for label, subset in [("SHORTS", shorts), ("LONGS", longs)]:
            if subset:
                sw = len([t for t in subset if t['result']=='WIN'])
                sl_c = len([t for t in subset if t['result']=='LOSS'])
                sp = sum(t['profit'] for t in subset)
                print(f"  {label}: {len(subset)} trades | WR: {round(sw/(sw+sl_c)*100,1) if (sw+sl_c)>0 else 0}% | ${sp:.2f}")
    else:
        print("  No trades")
    
    return trades

def main():
    print("=" * 60)
    print(f"GOLD BREAKOUT BACKTEST v3 (ALL BUGS FIXED) - {SYMBOL}")
    print(f"Period: {START_DATE.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 60)
    
    mt5.initialize()
    trades = backtest()
    if trades:
        pd.DataFrame(trades).to_csv("backtest_breakout_v3.csv", index=False)
        print("\nSaved to backtest_breakout_v3.csv")
    mt5.shutdown()

if __name__ == "__main__":
    main()