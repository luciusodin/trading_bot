"""
Walk-Forward Test - Gold Breakout on 2025 Data (FIXED)
Patched: copy_rates_range for correct dates & strict intra-candle wick protection
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

SYMBOL = "XAUUSD"
START_DATE = datetime(2025, 3, 27)
END_DATE = datetime(2025, 6, 25)
TRAIL_START = 3.0
TRAIL_DIST = 1.5
SPREAD_COST = 0.30  # Fixed simulation spread drag

def get_daily_data():
    # Corrected time window fetch
    rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_D1, START_DATE, END_DATE)
    if rates is None or len(rates) == 0: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def get_5m_data():
    # FIXED: copy_rates_range ensures data moves FORWARD from START_DATE to END_DATE
    rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, START_DATE, END_DATE)
    if rates is None or len(rates) == 0: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def simulate_trade(df_full, start_idx, direction, entry_price, stop_loss):
    highest_profit = 0
    trailing_sl = stop_loss
    in_position = False
    
    for i in range(start_idx + 1, len(df_full)):
        high = float(df_full['high'].iloc[i])
        low = float(df_full['low'].iloc[i])
        
        # Trigger entry logic first
        if not in_position:
            filled = (low <= entry_price) if direction == "SHORT" else (high >= entry_price)
            if not filled: continue
            in_position = True
            
            # Initial defensive scan on the entry candle itself
            if direction == "SHORT" and high >= stop_loss:
                return "LOSS", round(-(abs(entry_price - stop_loss) + SPREAD_COST), 2), df_full.index[i]
            if direction == "LONG" and low <= stop_loss:
                return "LOSS", round(-(abs(entry_price - stop_loss) + SPREAD_COST), 2), df_full.index[i]
        
        # FIXED: Pessimistic Intra-Candle Wick Evaluation
        if direction == "SHORT":
            # 1. Check if the current trailing stop is hit by the high wick BEFORE updating the trail
            if high >= trailing_sl:
                pnl = entry_price - trailing_sl - SPREAD_COST
                return ("WIN" if pnl > 0 else "LOSS"), round(pnl, 2), df_full.index[i]
            
            # 2. Update trailing stop after safe wick validation
            profit = entry_price - low
            if profit >= TRAIL_START:
                new_sl = low + TRAIL_DIST
                trailing_sl = min(trailing_sl, new_sl)
                
        else:  # LONG
            # 1. Check if the low wick hits the trailing stop before looking at new highs
            if low <= trailing_sl:
                pnl = trailing_sl - entry_price - SPREAD_COST
                return ("WIN" if pnl > 0 else "LOSS"), round(pnl, 2), df_full.index[i]
            
            # 2. Update trailing stop safely
            profit = high - entry_price
            if profit >= TRAIL_START:
                new_sl = high - TRAIL_DIST
                trailing_sl = max(trailing_sl, new_sl)
                
    return ("OPEN", round(highest_profit, 2), df_full.index[-1]) if in_position else ("UNFILLED", 0, df_full.index[-1])

def backtest():
    print(f"\nBacktesting {SYMBOL} Breakout on 2025 Data...")
    print(f"Trail Start: ${TRAIL_START} | Trail Distance: ${TRAIL_DIST}\n")
    
    daily = get_daily_data()
    m5 = get_5m_data()
    
    if daily is None or m5 is None:
        print("Not enough data to parse.")
        return []
    
    trades = []
    for i in range(1, len(daily)):
        prev_high = float(daily['high'].iloc[i-1])
        prev_low = float(daily['low'].iloc[i-1])
        
        day_start = daily['time'].iloc[i]
        
        # Verify the day exists inside our granular M5 dataframe pool
        if day_start not in m5.index:
            continue
            
        day_start_idx = m5.index.get_indexer([day_start], method='nearest')[0]
        day_end = day_start + timedelta(days=1)
        day_end_idx = m5.index.get_indexer([day_end], method='nearest')[0]
        day_end_idx = min(day_end_idx, len(m5) - 1)
        
        for j in range(day_start_idx + 10, day_end_idx):
            high = float(m5['high'].iloc[j])
            low = float(m5['low'].iloc[j])
            
            if low < prev_low:
                entry = prev_low - 0.5
                stop = prev_high
                result, profit, exit_time = simulate_trade(m5, j, "SHORT", entry, stop)
                
                if result != "UNFILLED":
                    trades.append({'date': day_start.strftime("%Y-%m-%d"), 'direction': 'SHORT',
                                   'entry': entry, 'stop': stop, 'result': result, 'profit': profit})
                if result not in ["UNFILLED", "OPEN"]:
                    j = m5.index.get_indexer([exit_time], method='nearest')[0]
                break
            
            elif high > prev_high:
                entry = prev_high + 0.5
                stop = prev_low
                result, profit, exit_time = simulate_trade(m5, j, "LONG", entry, stop)
                
                if result != "UNFILLED":
                    trades.append({'date': day_start.strftime("%Y-%m-%d"), 'direction': 'LONG',
                                   'entry': entry, 'stop': stop, 'result': result, 'profit': profit})
                if result not in ["UNFILLED", "OPEN"]:
                    j = m5.index.get_indexer([exit_time], method='nearest')[0]
                break
    
    if trades:
        wins = [t for t in trades if t['result'] == 'WIN']
        losses = [t for t in trades if t['result'] == 'LOSS']
        tp = sum(t['profit'] for t in wins) if wins else 0
        tl = abs(sum(t['profit'] for t in losses)) if losses else 0
        r = len(wins) + len(losses)
        wr = round(len(wins)/r*100, 1) if r > 0 else 0
        pf = round(tp/tl, 2) if tl > 0 else tp
        
        print(f"  2025 Results: {len(trades)} trades | W:{len(wins)} L:{len(losses)} | WR:{wr}% | PF:{pf} | Net: ${tp-tl:.2f}")
        print(f"\n  COMPARISON ENGINE:")
        print(f"  2026: 172 trades | 98.8% WR | +$2,734 (Potentially Overfitted/Blind)")
        print(f"  2025: {len(trades)} trades | {wr}% WR | Net P&L: ${tp-tl:.2f}")
        
        if wr > 70:
            print(f"\n  ✅ Strategy ROBUST across changing market cycles!")
        elif wr > 45:
            print(f"\n  ⚠️ Strategy remains profitable but edge is normalized. Standard overfitting observed.")
        else:
            print(f"\n  ❌ Strategy FAILS under strict intra-candle wicks. Redesign parameters.")
    else:
        print("  No trades detected in sample data.")
        
    return trades

def main():
    print("=" * 60)
    print("WALK-FORWARD STRESS TEST ENGINE (V40 FIXED)")
    print(f"Window: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print("=" * 60)
    
    if not mt5.initialize():
        print("MT5 Initialization Failed")
        return
        
    trades = backtest()
    if trades:
        pd.DataFrame(trades).to_csv("backtest_2025_fixed.csv", index=False)
    mt5.shutdown()

if __name__ == "__main__":
    main()