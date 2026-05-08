import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_ema(df):
    if df.empty:
        return df

    close_prices = df['Close']
    if isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]

    df['EMA10'] = ta.ema(close_prices, length=10)
    df['EMA20'] = ta.ema(close_prices, length=20)
    df['EMA50'] = ta.ema(close_prices, length=50)
    df['EMA200'] = ta.ema(close_prices, length=200)
    return df

def is_cup_and_handle(df):
    """
    Identifies Cup and Handle pattern.
    - Cup: 1 month+ duration.
    - Handle: Retracement not exceeding 50% of cup depth.
    Simplified logic: Look for a significant high, a dip (cup), a return to near high, and a smaller dip (handle).
    """
    if len(df) < 60: # Need enough data for 1 month cup + handle
        return False

    # Using last 60-120 days for analysis
    close_prices = df['Close']
    if isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]

    prices = close_prices.tail(120).values
    n = len(prices)

    # 1. Find the left high of the cup (peak in the first half of the period)
    left_period = prices[:n//2]
    left_high_idx = np.argmax(left_period)
    left_high = left_period[left_high_idx]

    # 2. Find the bottom of the cup (minimum after the left high)
    cup_period = prices[left_high_idx:int(n*0.8)]
    if len(cup_period) < 20: return False # At least 1 month approx

    cup_bottom_idx = np.argmin(cup_period) + left_high_idx
    cup_bottom = prices[cup_bottom_idx]

    # 3. Find the right lip of the cup (a peak after the bottom, near the left high)
    right_lip_period = prices[cup_bottom_idx:int(n*0.9)]
    if len(right_lip_period) < 5: return False
    right_lip_idx = np.argmax(right_lip_period) + cup_bottom_idx
    right_lip = prices[right_lip_idx]

    # Check if right lip is near left high (within 10%)
    if abs(right_lip - left_high) / left_high > 0.10:
        return False

    # 4. Handle check: Small retracement after right lip
    handle_period = prices[right_lip_idx:]
    if len(handle_period) < 3: return False

    handle_bottom = np.min(handle_period)
    cup_depth = left_high - cup_bottom
    handle_depth = right_lip - handle_bottom

    # Handle depth should not exceed 50% of cup depth
    if handle_depth > 0.5 * cup_depth or handle_depth < 0:
        return False

    return True

def is_range_breakout(df):
    """
    Range Breakout: Consolidation for 1 month+ within 20% range, then breaking out.
    """
    if len(df) < 30: return False

    # Ensure we are working with a 1D Series
    close_prices = df['Close']
    if isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]

    # Last 20-30 days for consolidation range
    consolidation_period = close_prices.iloc[-30:-1]
    highest = consolidation_period.max()
    lowest = consolidation_period.min()

    # Range check
    price_range_pct = (highest - lowest) / lowest
    if (price_range_pct > 0.20).any() if isinstance(price_range_pct, pd.Series) else price_range_pct > 0.20:
        return False

    # Breakout check
    current_price = close_prices.iloc[-1]
    if (current_price > highest).any() if isinstance(current_price, pd.Series) else current_price > highest:
        return True

    return False

def is_tight_setup(stock_df, sector_df):
    """
    Tight Setup: Stock holding up within 3% of 5-day high
    while sectoral index drops > 2% over last 5 days.
    """
    if len(stock_df) < 5 or len(sector_df) < 5:
        return False

    # Sector drop check
    sector_close = sector_df['Close']
    if isinstance(sector_close, pd.DataFrame):
        sector_close = sector_close.iloc[:, 0]

    sector_drop = (sector_close.iloc[-1] - sector_close.iloc[-5]) / sector_close.iloc[-5]

    if (sector_drop > -0.02).any() if isinstance(sector_drop, pd.Series) else sector_drop > -0.02: # Needs to drop more than 2%
        return False

    # Stock holding up check
    stock_close = stock_df['Close']
    if isinstance(stock_close, pd.DataFrame):
        stock_close = stock_close.iloc[:, 0]

    stock_5d_high = stock_close.iloc[-5:].max()
    stock_current = stock_close.iloc[-1]

    # Within 3% of 5-day high
    diff_pct = (stock_5d_high - stock_current) / stock_5d_high
    if (diff_pct < 0.03).any() if isinstance(diff_pct, pd.Series) else diff_pct < 0.03:
        return True

    return False
