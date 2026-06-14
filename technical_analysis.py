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
    IPO Breakout Strategy:
    1. Selection: IPO within last 12 months (handled in app.py).
    2. Liquidity: Avg daily volume > 75k (last 20 days).
    3. Consolidation: Tight range (approx 5% to 8%) for up to 4 months.
    4. Entry: Breakout of ATH with bullish candle 3% to 5%.
    """
    if len(df) < 10: return False, {}

    close_prices = df['Close']
    high_prices = df['High']
    low_prices = df['Low']
    volumes = df['Volume']

    if isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]
        high_prices = high_prices.iloc[:, 0]
        low_prices = low_prices.iloc[:, 0]
        volumes = volumes.iloc[:, 0]

    # Liquidity check
    avg_volume = volumes.tail(20).mean()
    if avg_volume < 75000:
        return False, {}

    # ATH excluding the most recent candle
    breakout_window = 1
    historic_ath = high_prices.iloc[:-breakout_window].max()

    current_price = close_prices.iloc[-1]
    prev_price = close_prices.iloc[-2]

    # Consolidation: up to 4 months (approx 80 trading days)
    # We look at the period before the breakout window
    lookback = min(80, len(df) - breakout_window)
    if lookback < 5: return False, {}

    consol_period_high = high_prices.iloc[-lookback-breakout_window : -breakout_window].max()
    consol_period_low = low_prices.iloc[-lookback-breakout_window : -breakout_window].min()
    consol_range_pct = (consol_period_high - consol_period_low) / consol_period_high

    # Requirement: Consolidation range approximately 5% to 8%
    # Using a slightly wider range [0.04, 0.09] to capture "approximately"
    if not (0.04 <= consol_range_pct <= 0.09):
        return False, {}

    # Entry Trigger: Breakout of ATH with bullish candle 3% to 5%
    is_ath_breakout = current_price > historic_ath
    candle_change = (current_price - prev_price) / prev_price
    # Requirement: Bullish candle of 3% to 5%
    # Again, allowing slight flexibility [0.028, 0.055]
    is_bullish_candle = (0.028 <= candle_change <= 0.055)

    if is_ath_breakout and is_bullish_candle:
        return True, {
            'start': df.index[-lookback-breakout_window],
            'end': df.index[-1],
            'label': 'IPO Breakout',
            'status': 'Broken',
            'breakout_price': float(historic_ath)
        }

    # Verge Check: Within 2% of ATH and meets consolidation criteria
    if current_price >= historic_ath * 0.98 and current_price <= historic_ath:
        return True, {
            'start': df.index[-lookback-breakout_window],
            'end': df.index[-1],
            'label': 'IPO (Verge)',
            'status': 'Verge',
            'breakout_price': float(historic_ath)
        }

    return False, {}

def is_volume_price_spike(df):
    """
    Volume & Price Spike:
    - Current day price increase >= 3%
    - Current day volume >= 1.5x of 20-day average volume.
    """
    if len(df) < 21: return False, {}

    close_prices = df['Close']
    volumes = df['Volume']

    if isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]
        volumes = volumes.iloc[:, 0]

    current_price = close_prices.iloc[-1]
    prev_price = close_prices.iloc[-2]
    current_volume = volumes.iloc[-1]
    avg_volume = volumes.tail(21).iloc[:-1].mean() # Average of previous 20 days

    price_change_pct = (current_price - prev_price) / prev_price
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

    if price_change_pct >= 0.03 and volume_ratio >= 1.5:
        return True, {
            'start': df.index[-1],
            'end': df.index[-1],
            'label': f"Spike (+{price_change_pct*100:.1f}%, {volume_ratio:.1f}x Vol)",
            'status': 'Broken', # Highlighting the spike
            'breakout_price': float(prev_price)
        }

    return False, {}

def is_double_bottom(df):
    """
    Double Bottom Reversal Pattern:
    1. Downtrend: Price below 50 EMA before pattern starts.
    2. "W" Shape: Two bottoms within 3% range of each other.
    3. Duration: Pattern forms within approx 3 months (60 sessions).
    4. Neckline: Highest point between the two bottoms.
    5. Breakout: Price crosses neckline with volume > 1.2x average.
    """
    if len(df) < 60: return False, {}

    if 'EMA50' not in df.columns:
        df = calculate_ema(df)

    close_prices = df['Close']
    low_prices = df['Low']
    high_prices = df['High']
    volumes = df['Volume']
    ema50 = df['EMA50']

    if isinstance(close_prices, pd.DataFrame):
        close_prices = close_prices.iloc[:, 0]
        low_prices = low_prices.iloc[:, 0]
        high_prices = high_prices.iloc[:, 0]
        volumes = volumes.iloc[:, 0]
        ema50 = ema50.iloc[:, 0]

    lookback = 60 # 3 months approx
    prices_subset = close_prices.tail(lookback)
    lows_subset = low_prices.tail(lookback)
    highs_subset = high_prices.tail(lookback)

    # 1. Check for Downtrend before pattern (Price below 50 EMA)
    idx_start = len(df) - lookback
    # Check if price was below EMA50 at the start of our lookback period
    if close_prices.iloc[idx_start] > ema50.iloc[idx_start]:
        return False, {}

    # 2. Find two bottoms
    # Divide lookback into two halves to find two distinct bottom candidates
    first_half = lows_subset.iloc[:lookback//2]
    second_half = lows_subset.iloc[lookback//2:]

    b1_idx = first_half.argmin()
    b1_price = first_half.iloc[b1_idx]
    b1_idx_abs = lows_subset.index.get_loc(first_half.index[b1_idx])

    b2_idx = second_half.argmin()
    b2_price = second_half.iloc[b2_idx]
    b2_idx_abs = lows_subset.index.get_loc(second_half.index[b2_idx])

    # Bottoms proximity check (within 3%)
    if abs(b1_price - b2_price) / max(b1_price, b2_price) > 0.03:
        return False, {}

    # 3. Find Neckline (highest point between b1 and b2)
    between_bottoms = highs_subset.iloc[b1_idx_abs : b2_idx_abs]
    if len(between_bottoms) < 5: return False, {}

    neckline_price = between_bottoms.max()

    current_price = close_prices.iloc[-1]
    avg_volume = volumes.tail(20).mean()
    current_volume = volumes.iloc[-1]

    # 4. Breakout Check
    if current_price > neckline_price:
        if current_volume > avg_volume * 1.2:
            return True, {
                'start': lows_subset.index[b1_idx_abs],
                'end': lows_subset.index[-1],
                'label': 'Double Bottom',
                'status': 'Broken',
                'breakout_price': float(neckline_price)
            }

    # 5. Verge Check
    if current_price >= neckline_price * 0.98 and current_price <= neckline_price:
        return True, {
            'start': lows_subset.index[b1_idx_abs],
            'end': lows_subset.index[-1],
            'label': 'Double Bottom (Verge)',
            'status': 'Verge',
            'breakout_price': float(neckline_price)
        }

    return False, {}
