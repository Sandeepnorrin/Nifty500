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

    # Volume check for breakout
    volumes = df['Volume']
    if isinstance(volumes, pd.DataFrame): volumes = volumes.iloc[:, 0]
    avg_volume = volumes.tail(20).mean()
    curr_volume = volumes.iloc[-1]

    # Check if broken or on verge
    if current_price > left_high:
        # For broken, we need volume spike
        if curr_volume < avg_volume:
            return False, {}
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
            # Volume check for range breakout
            volumes = df['Volume']
            if isinstance(volumes, pd.DataFrame): volumes = volumes.iloc[:, 0]
            avg_volume = volumes.tail(20).mean()

            # Check if volume was above average during the breakout sessions
            recent_vols = volumes.tail(recent_lookback)
            if not (recent_vols > avg_volume).any():
                continue

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
    stock_high = stock_df['High']
    if isinstance(stock_close, pd.DataFrame):
        stock_close = stock_close.iloc[:, 0]
    if isinstance(stock_high, pd.DataFrame):
        stock_high = stock_high.iloc[:, 0]

    stock_recent_high = stock_high.iloc[-5:].max()
    stock_current = stock_close.iloc[-1]

    # Within 3.5% of recent high (slightly relaxed from 3%)
    diff_pct = (stock_recent_high - stock_current) / stock_recent_high

    if hasattr(diff_pct, 'any'):
        found = (diff_pct < 0.035).any()
    else:
        found = diff_pct < 0.035

    # Volume check: Tight setup should have near average or lower volume (not a huge spike or dry)
    volumes = stock_df['Volume']
    if isinstance(volumes, pd.DataFrame): volumes = volumes.iloc[:, 0]
    avg_volume = volumes.tail(20).mean()
    curr_volume = volumes.iloc[-1]

    # "Near average" defined as between 0.5x and 1.5x
    is_volume_tight = (curr_volume >= avg_volume * 0.5) and (curr_volume <= avg_volume * 1.5)

    if found and is_volume_tight:
        region = {
            'start': stock_df.index[-5],
            'end': stock_df.index[-1],
            'label': 'Tight Setup',
            'status': 'Verge', # Tight setup is generally a consolidation/verge pattern
            'breakout_price': float(stock_recent_high)
        }
        return True, region

    return False, {}

def is_ema_aligned(df):
    """
    Checks if EMA20 > EMA50 > EMA200 for the latest candle.
    """
    if df.empty or 'EMA20' not in df.columns or 'EMA50' not in df.columns or 'EMA200' not in df.columns:
        return False

    last = df.iloc[-1]

    # Check for NaN
    if pd.isna(last['EMA20']) or pd.isna(last['EMA50']) or pd.isna(last['EMA200']):
        return False

    return last['EMA20'] > last['EMA50'] and last['EMA50'] > last['EMA200']

def is_52w_high_breakout(df):
    """
    52W High Breakout with Volume:
    - Current price > 52-week high (excluding recent sessions).
    - Volume > 20-period average volume.
    - Verge: Within 10% of 52W high OR sudden green candles with huge volume.
    """
    if len(df) < 252: return False, {}

    close_prices = df['Close']
    high_prices = df['High']
    volumes = df['Volume']

    if isinstance(close_prices, pd.DataFrame): close_prices = close_prices.iloc[:, 0]
    if isinstance(high_prices, pd.DataFrame): high_prices = high_prices.iloc[:, 0]
    if isinstance(volumes, pd.DataFrame): volumes = volumes.iloc[:, 0]

    # Calculate 52W high (excluding last 5 sessions to identify the 'peak' to break)
    lookback_52w = 252
    historic_52w_high = high_prices.iloc[-lookback_52w:-5].max()

    avg_volume = volumes.tail(20).mean()
    curr_volume = volumes.iloc[-1]
    curr_price = close_prices.iloc[-1]

    # 1. Breakout check
    if curr_price > historic_52w_high and curr_volume > avg_volume:
        region = {
            'start': df.index[-5],
            'end': df.index[-1],
            'label': '52W High Breakout (Vol)',
            'status': 'Broken',
            'breakout_price': float(historic_52w_high)
        }
        return True, region

    # 2. On the Verge check:
    # Method A: Price is consolidating near 10% of 52W high
    is_near_high = curr_price >= historic_52w_high * 0.90

    # Method B: Sudden green candles with huge volume (last 3 sessions)
    recent_vols = volumes.tail(3)
    recent_closes = close_prices.tail(3)
    recent_opens = df['Open'].tail(3)
    if isinstance(recent_opens, pd.DataFrame): recent_opens = recent_opens.iloc[:, 0]

    huge_vol_spike = (recent_vols > avg_volume * 2).any()
    green_candles = (recent_closes > recent_opens).any()

    if is_near_high or (huge_vol_spike and green_candles):
        region = {
            'start': df.index[-5],
            'end': df.index[-1],
            'label': '52W High (Verge)',
            'status': 'Verge',
            'breakout_price': float(historic_52w_high)
        }
        return True, region

    return False, {}

def is_ipo_breakout(df):
    """
    IPO Breakout Pattern:
    - Identifies stocks breaking out of their All-Time High (ATH).
    - Usually after a consolidation period since listing.
    - Confirmation by above-average volume.
    """
    if len(df) < 10: return False, {}

    close_prices = df['Close']
    high_prices = df['High']
    volumes = df['Volume']

    if isinstance(close_prices, pd.Series):
        pass
    elif isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]
        high_prices = high_prices.iloc[:, 0]
        volumes = volumes.iloc[:, 0]

    # Use a small window for the current "breakout" attempt
    breakout_window = 3
    if len(df) <= breakout_window: return False, {}

    # All-time high BEFORE the current breakout window
    historic_ath = high_prices.iloc[:-breakout_window].max()

    current_price = close_prices.iloc[-1]
    avg_volume = volumes.tail(20).mean()
    current_volume = volumes.iloc[-1]

    # Breakout criteria
    is_breakout = current_price > historic_ath
    is_good_volume = current_volume > avg_volume

    # Consolidation check: Price should have spent at least 5 days below ATH
    # before breaking out (prevents just a straight line up)
    prices_below_ath = (high_prices.iloc[:-breakout_window] <= historic_ath).all()
    # Actually historic_ath IS the max of that period, so it's always true.
    # Let's check if it was consolidating (e.g., within 25% of ATH)
    low_in_period = close_prices.iloc[:-breakout_window].min()
    was_consolidating = (historic_ath - low_in_period) / historic_ath < 0.30

    if is_breakout and is_good_volume and was_consolidating:
        region = {
            'start': df.index[0], # From listing
            'end': df.index[-1],
            'label': 'IPO ATH Breakout',
            'status': 'Broken',
            'breakout_price': float(historic_ath)
        }
        return True, region

    # Verge check
    if current_price >= historic_ath * 0.97 and current_price <= historic_ath and was_consolidating:
        region = {
            'start': df.index[0],
            'end': df.index[-1],
            'label': 'IPO ATH (Verge)',
            'status': 'Verge',
            'breakout_price': float(historic_ath)
        }
        return True, region

    return False, {}
