import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
import time

def get_nifty500_stocks():
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    try:
        df = pd.read_csv(url)
        return df
    except Exception as e:
        print(f"Error fetching Nifty 500 list: {e}")
        return pd.DataFrame()

def get_stock_fundamentals(symbol):
    """
    Scrapes ROE, ROCE and FII/DII holdings from Screener.in
    Note: Screener.in uses symbols without .NS suffix.
    """
    url = f"https://www.screener.in/company/{symbol}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        fundamentals = {}

        # Extract ROE and ROCE
        # They are usually in the top "company-info" or "top-ratios" section
        ratios_li = soup.find_all('li', class_='flex flex-space-between')
        for li in ratios_li:
            name_span = li.find('span', class_='name')
            if not name_span: continue
            name = name_span.text.strip()
            value_span = li.find('span', class_='value')
            if value_span:
                # Value might contain extra whitespace and %
                value = value_span.text.strip().split('\n')[0].replace(',', '').replace('%', '').strip()
                try:
                    if 'Return on equity' in name:
                        fundamentals['ROE'] = float(value)
                    elif 'ROCE' in name:
                        fundamentals['ROCE'] = float(value)
                except ValueError:
                    pass

        # Extract Shareholding Pattern (FII/DII)
        # We need past 3 quarters to see 2 QoQ increases
        shareholding_section = soup.find('section', id='shareholding')
        if shareholding_section:
            # Look for quarterly table
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
                            try:
                                fii_holdings.append(float(val or 0))
                            except ValueError:
                                fii_holdings.append(0.0)
                    elif 'DIIs' in row_name:
                        for c in cells[1:]:
                            val = c.text.strip().replace('%', '').strip()
                            try:
                                dii_holdings.append(float(val or 0))
                            except ValueError:
                                dii_holdings.append(0.0)

                fundamentals['FII_Holdings'] = fii_holdings[-4:] if len(fii_holdings) >= 4 else fii_holdings
                fundamentals['DII_Holdings'] = dii_holdings[-4:] if len(dii_holdings) >= 4 else dii_holdings

        return fundamentals
    except Exception as e:
        print(f"Error scraping fundamentals for {symbol}: {e}")
        return None

def get_price_data(symbol, period="1y", interval="1d"):
    """
    Fetches historical price data from Yahoo Finance.
    """
    # yfinance uses .NS for Indian stocks
    ticker = symbol + ".NS"
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        # Handle MultiIndex columns in newer yfinance versions
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except Exception as e:
        print(f"Error fetching price data for {symbol}: {e}")
        return pd.DataFrame()

def get_sector_data(sector_index_symbol, period="1y"):
    """
    Fetches historical price data for sectoral indices.
    """
    try:
        data = yf.download(sector_index_symbol + ".NS", period=period, progress=False)
        # Handle MultiIndex columns in newer yfinance versions
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except Exception as e:
        print(f"Error fetching sector data for {sector_index_symbol}: {e}")
        return pd.DataFrame()
