import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
import time

import os

NIFTY500_LIST_FILE = "nifty500_list.csv"

def get_nifty500_stocks(refresh=False):
    if not refresh and os.path.exists(NIFTY500_LIST_FILE):
        return pd.read_csv(NIFTY500_LIST_FILE)

    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    try:
        df = pd.read_csv(url)
        df.to_csv(NIFTY500_LIST_FILE, index=False)
        return df
    except Exception as e:
        print(f"Error fetching Nifty 500 list: {e}")
        if os.path.exists(NIFTY500_LIST_FILE):
            return pd.read_csv(NIFTY500_LIST_FILE)
        return pd.DataFrame()

def get_stock_fundamentals(symbol):
    """
    Scrapes ROE, ROCE and FII/DII holdings from Screener.in
    Note: Screener.in uses symbols without .NS suffix.
    """
    url = f"https://www.screener.in/company/{symbol}/"
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                fundamentals = {}

                # Extract ROE and ROCE
                ratios_li = soup.find_all('li', class_='flex flex-space-between')
                for li in ratios_li:
                    name_span = li.find('span', class_='name')
                    if not name_span: continue
                    name = name_span.text.strip()

                    value_span = li.find('span', class_='value')
                    if value_span:
                        number_span = value_span.find('span', class_='number')
                        if number_span:
                            value = number_span.text.strip()
                        else:
                            value = value_span.text.strip().split('\n')[0].replace(',', '').replace('%', '').strip()

                        try:
                            if name == 'ROE' or 'Return on equity' in name:
                                fundamentals['ROE'] = float(value)
                            elif name == 'ROCE':
                                fundamentals['ROCE'] = float(value)
                            elif 'Market Cap' in name:
                                fundamentals['Market Cap'] = float(value)
                        except ValueError:
                            pass

                # Extract Shareholding Pattern (FII/DII)
                shareholding_section = soup.find('section', id='shareholding')
                if shareholding_section:
                    table = shareholding_section.find('table', class_='data-table')
                    if table:
                        rows = table.find_all('tr')
                        fii_holdings = []
                        dii_holdings = []
                        for row in rows:
                            cells = row.find_all('td')
                            if not cells: continue
                            row_name = cells[0].text.strip()
                            if 'FIIs' in row_name:
                                for c in cells[1:]:
                                    val = c.text.strip().replace('%', '').strip()
                                    try: fii_holdings.append(float(val or 0))
                                    except ValueError: fii_holdings.append(0.0)
                            elif 'DIIs' in row_name:
                                for c in cells[1:]:
                                    val = c.text.strip().replace('%', '').strip()
                                    try: dii_holdings.append(float(val or 0))
                                    except ValueError: dii_holdings.append(0.0)
                        fundamentals['FII_Holdings'] = fii_holdings[-4:] if len(fii_holdings) >= 4 else fii_holdings
                        fundamentals['DII_Holdings'] = dii_holdings[-4:] if len(dii_holdings) >= 4 else dii_holdings

                return fundamentals

            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
            else:
                break
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"Error scraping fundamentals for {symbol} after {max_retries} attempts: {e}")
    return None

def get_price_data(symbol, period="1y", interval="1d"):
    """
    Fetches historical price data from Yahoo Finance.
    """
    ticker = symbol + ".NS"
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except Exception as e:
        print(f"Error fetching price data for {symbol}: {e}")
        return pd.DataFrame()

def get_sector_data(sector_index_symbol, period="2y", interval="1d"):
    """
    Fetches historical price data for sectoral indices.
    """
    try:
        symbol = sector_index_symbol
        if not symbol.startswith('^'):
            symbol += ".NS"
        data = yf.download(symbol, period=period, interval=interval, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except Exception as e:
        print(f"Error fetching sector data for {sector_index_symbol}: {e}")
        return pd.DataFrame()
