# Map NSE industries to YFinance/NSE sectoral indices
SECTOR_MAP = {
    'Financial Services': '^CNXFIN', # Nifty Financial Services
    'IT': '^CNXIT', # Nifty IT
    'Automobile and Auto Components': '^CNXAUTO', # Nifty Auto
    'Bank': '^NSEBANK', # Nifty Bank
    'Consumer Durables': '^CNXCONSR', # Nifty Consumer Durables
    'Fast Moving Consumer Goods': '^CNXFMCG', # Nifty FMCG
    'Healthcare': '^CNXPHARMA', # Nifty Pharma
    'Oil Gas & Consumable Fuels': '^CNXENERGY', # Nifty Energy (approx)
    'Metals & Mining': '^CNXMETAL', # Nifty Metal
    'Realty': '^CNXREALTY', # Nifty Realty
    'Media Entertainment & Publication': '^CNXMEDIA', # Nifty Media
    'Services': '^CNXSERVICE', # Nifty Services
    'Telecommunication': '^CNXIT', # Mapping to IT for lack of better
}

def get_sector_index(industry):
    return SECTOR_MAP.get(industry, '^NSEI') # Default to Nifty 50 if no specific sector found
