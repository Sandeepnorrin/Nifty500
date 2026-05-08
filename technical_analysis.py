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
    Returns: (bool, dict region_info)
    """
    if len(df) < 60:
        return False, {}

    close_prices = df['Close']
    if isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]

    n_total = len(close_prices)
    lookback = 120
    prices = close_prices.tail(lookback).values
    n = len(prices)

    # Indices in the 'prices' array
    left_period = prices[:n//2]
    left_high_idx = np.argmax(left_period)

    cup_period = prices[left_high_idx:int(n*0.8)]
    if len(cup_period) < 20: return False, {}

    cup_bottom_idx = np.argmin(cup_period) + left_high_idx

    right_lip_period = prices[cup_bottom_idx:int(n*0.9)]
    if len(right_lip_period) < 5: return False, {}
    right_lip_idx = np.argmax(right_lip_period) + cup_bottom_idx

    if abs(prices[right_lip_idx] - prices[left_high_idx]) / prices[left_high_idx] > 0.10:
        return False, {}

    handle_period = prices[right_lip_idx:]
    if len(handle_period) < 3: return False, {}

    handle_bottom = np.min(handle_period)
    cup_depth = prices[left_high_idx] - prices[cup_bottom_idx]
    handle_depth = prices[right_lip_idx] - handle_bottom

    if handle_depth > 0.5 * cup_depth or handle_depth < 0:
        return False, {}

    # Convert local prices array indices back to df index
    start_idx = n_total - n + left_high_idx
    end_idx = n_total - 1

    current_price = close_prices.iloc[-1]
    left_high = prices[left_high_idx]

    # Check if broken or on verge
    if current_price > left_high:
        status = 'Broken'
        label = 'Cup and Handle'
    elif current_price >= left_high * 0.98:
        status = 'Verge'
        label = 'Cup & Handle (Verge)'
    else:
        # If it's too far from the high, it's not "on the verge" yet.
        return False, {}

    region = {
        'start': df.index[start_idx],
        'end': df.index[end_idx],
        'label': label,
        'status': status,
        'breakout_price': float(left_high)
    }
    return True, region

def is_range_breakout(df):
    """
    Range Breakout (Updated):
    - High formed and not broken for at least 20 trading sessions.
    - Price dips by max 25% from that high during this period.
    - Eventually current price breaks that high.
    """
    if len(df) < 25: return False, {}

    close_prices = df['Close']
    if isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]

    # We need to find a peak that hasn't been broken for at least 20 sessions
    # and check the criteria against the current price breakout.

    # Look back for potential peaks between 21 and 60 sessions ago
    recent_lookback = 3
    n_total = len(df)
    for lookback in range(21, min(61, n_total)):
        peak_idx_abs = n_total - lookback
        peak_price = close_prices.iloc[peak_idx_abs]

        # 1. Check if this peak was a local high (higher than or equal to immediate neighbors)
        # We use strictly greater to avoid flat tops being picked as multiple peaks
        if peak_price <= close_prices.iloc[peak_idx_abs-1] or peak_price <= close_prices.iloc[peak_idx_abs+1]:
            continue

        # 2. Check if this high was NOT broken for at least 20 sessions AFTER it was formed,
        # but BEFORE the recent breakout sessions.
        period_after_peak = close_prices.iloc[peak_idx_abs+1 : -recent_lookback]
        if len(period_after_peak) < 15: continue

        if (period_after_peak.max() > peak_price).any():
            continue

        # 3. Check if the price dipped by max 25% from that high during this period
        period_min = period_after_peak.min()
        dip_pct = (peak_price - period_min) / peak_price
        if dip_pct > 0.25:
            continue

        # 4. Breakout check: any price in last 'recent_lookback' sessions breaks the peak price
        recent_prices = close_prices.tail(recent_lookback)
        if (recent_prices > peak_price).any():
            region = {
                'start': df.index[peak_idx_abs],
                'end': df.index[-1],
                'label': 'Range Breakout',
                'status': 'Broken',
                'breakout_price': float(peak_price)
            }
            return True, region

        # 5. On the Verge check: current price is within 2% of peak_price but hasn't broken it
        current_price = close_prices.iloc[-1]
        if current_price <= peak_price and current_price >= peak_price * 0.98:
            region = {
                'start': df.index[peak_idx_abs],
                'end': df.index[-1],
                'label': 'Breakout (Verge)',
                'status': 'Verge',
                'breakout_price': float(peak_price)
            }
            return True, region

    return False, {}

def is_tight_setup(stock_df, sector_df):
    """
    Tight Setup: Stock holding up within 3% of recent high (5 periods)
    while sectoral index drops > 2% over last 5 periods.
    """
    if len(stock_df) < 5 or len(sector_df) < 5:
        return False, {}

    # Sector drop check
    sector_close = sector_df['Close']
    if isinstance(sector_close, pd.DataFrame):
        sector_close = sector_close.iloc[:, 0]

    # Find the matching dates or just use the last 5 periods if indices align
    # For simplicity, we assume they align or we just compare the last 5 available candles
    sector_drop = (sector_close.iloc[-1] - sector_close.iloc[-5]) / sector_close.iloc[-5]

    # We want sector_drop < -0.02 (more than 2% drop)
    # Using np.any() or similar to handle potential series, but it should be a scalar here
    if hasattr(sector_drop, 'any'):
        if not (sector_drop < -0.02).any():
            return False, {}
    else:
        if sector_drop >= -0.02:
            return False, {}

    # Stock holding up check
    stock_close = stock_df['Close']
    if isinstance(stock_close, pd.DataFrame):
        stock_close = stock_close.iloc[:, 0]

    stock_recent_high = stock_close.iloc[-5:].max()
    stock_current = stock_close.iloc[-1]

    # Within 3.5% of recent high (slightly relaxed from 3%)
    diff_pct = (stock_recent_high - stock_current) / stock_recent_high

    if hasattr(diff_pct, 'any'):
        found = (diff_pct < 0.035).any()
    else:
        found = diff_pct < 0.035

    if found:
        region = {
            'start': stock_df.index[-5],
            'end': stock_df.index[-1],
            'label': 'Tight Setup'
        }
        return True, region

    return False, {}
