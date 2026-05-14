import requests
import json
from datetime import datetime

class NotionSync:
    def __init__(self, api_key, database_id):
        self.api_key = api_key
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

    def query_stock(self, stock_name, breakout_price):
        """
        Queries the database for an existing record with the same stock name and breakout price.
        """
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        filter_data = {
            "filter": {
                "and": [
                    {
                        "property": "Stock name",
                        "title": {
                            "equals": stock_name
                        }
                    },
                    {
                        "property": "Breakout Price",
                        "number": {
                            "equals": float(breakout_price)
                        }
                    }
                ]
            }
        }

        response = requests.post(url, headers=self.headers, json=filter_data)
        if response.status_code == 200:
            results = response.json().get("results", [])
            return results[0] if results else None
        else:
            error_text = response.text
            print(f"Error querying Notion: {error_text}")
            raise Exception(f"Notion API Error: {error_text}")

    def create_record(self, data):
        """
        Creates a new record in the Notion database.
        data: dict containing stock info
        """
        url = "https://api.notion.com/v1/pages"

        properties = {
            "Stock name": {"title": [{"text": {"content": data['symbol']}}]},
            "Breakout Type": {"select": {"name": data['patterns']}},
            "Breakout Price": {"number": float(data['breakout_price'])},
            "CMP": {"number": float(data['current_price'])},
            "Broken out ?": {"checkbox": data['is_broken']},
            "15% Target achieved": {"checkbox": data['is_target_met']},
            "Notion entry date": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}}
        }

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties
        }

        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code != 200:
             raise Exception(f"Notion Create Error: {response.text}")
        return True

    def update_record(self, page_id, data):
        """
        Updates an existing record in Notion.
        """
        url = f"https://api.notion.com/v1/pages/{page_id}"

        properties = {
            "CMP": {"number": float(data['current_price'])},
            "Broken out ?": {"checkbox": data['is_broken']},
            "15% Target achieved": {"checkbox": data['is_target_met']}
        }

        payload = {"properties": properties}
        response = requests.patch(url, headers=self.headers, json=payload)
        if response.status_code != 200:
             raise Exception(f"Notion Update Error: {response.text}")
        return True

    def sync_stocks(self, stocks_list):
        """
        Main entry point to sync a list of stocks to Notion.
        stocks_list: list of dicts with keys: symbol, patterns, breakout_price, current_price
        """
        success_count = 0
        for stock in stocks_list:
            # Basic validation
            if not stock.get('breakout_price') or stock.get('breakout_price') <= 0:
                continue

            # Logic for flags
            is_broken = stock['current_price'] > stock['breakout_price']
            is_target_met = stock['current_price'] >= (stock['breakout_price'] * 1.15)

            stock['is_broken'] = is_broken
            stock['is_target_met'] = is_target_met

            existing = self.query_stock(stock['symbol'], stock['breakout_price'])
            if existing:
                if self.update_record(existing['id'], stock):
                    success_count += 1
            else:
                if self.create_record(stock):
                    success_count += 1
        return success_count
