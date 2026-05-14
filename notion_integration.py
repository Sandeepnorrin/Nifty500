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
        self.prop_map = {}

    def _get_property_names(self):
        """
        Fetches database metadata to map internal keys to actual property names.
        """
        url = f"https://api.notion.com/v1/databases/{self.database_id}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            props = response.json().get("properties", {})
            names = list(props.keys())

            # Map based on best match
            mapping = {}
            for n in names:
                low = n.lower().strip()
                if "stock" in low: mapping['stock'] = n
                elif "breakout" in low and "type" in low: mapping['type'] = n
                elif "breakout" in low and "price" in low: mapping['price'] = n
                elif "cmp" in low or ("current" in low and "price" in low): mapping['cmp'] = n
                elif "broken" in low: mapping['broken'] = n
                elif "15%" in low or "target" in low: mapping['target'] = n
                elif "date" in low: mapping['date'] = n

            self.prop_map = mapping
            return True
        return False

    def query_stock(self, stock_name, breakout_price):
        """
        Queries the database for an existing record with the same stock name and breakout price.
        """
        if not self.prop_map:
            self._get_property_names()

        stock_prop = self.prop_map.get('stock', 'Stock name')
        price_prop = self.prop_map.get('price', 'Breakout Price')

        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        filter_data = {
            "filter": {
                "and": [
                    {
                        "property": stock_prop,
                        "title": {
                            "equals": stock_name
                        }
                    },
                    {
                        "property": price_prop,
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
        if not self.prop_map:
            self._get_property_names()

        url = "https://api.notion.com/v1/pages"

        properties = {}
        if 'stock' in self.prop_map: properties[self.prop_map['stock']] = {"title": [{"text": {"content": data['symbol']}}]}
        if 'type' in self.prop_map: properties[self.prop_map['type']] = {"select": {"name": data['patterns']}}
        if 'price' in self.prop_map: properties[self.prop_map['price']] = {"number": float(data['breakout_price'])}
        if 'cmp' in self.prop_map: properties[self.prop_map['cmp']] = {"number": float(data['current_price'])}
        if 'broken' in self.prop_map: properties[self.prop_map['broken']] = {"checkbox": data['is_broken']}
        if 'target' in self.prop_map: properties[self.prop_map['target']] = {"checkbox": data['is_target_met']}
        if 'date' in self.prop_map: properties[self.prop_map['date']] = {"date": {"start": datetime.now().strftime("%Y-%m-%d")}}

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
        if not self.prop_map:
            self._get_property_names()

        url = f"https://api.notion.com/v1/pages/{page_id}"

        properties = {}
        if 'cmp' in self.prop_map: properties[self.prop_map['cmp']] = {"number": float(data['current_price'])}
        if 'broken' in self.prop_map: properties[self.prop_map['broken']] = {"checkbox": data['is_broken']}
        if 'target' in self.prop_map: properties[self.prop_map['target']] = {"checkbox": data['is_target_met']}

        payload = {"properties": properties}
        response = requests.patch(url, headers=self.headers, json=payload)
        if response.status_code != 200:
             raise Exception(f"Notion Update Error: {response.text}")
        return True

    def test_connection(self):
        """
        Tests the connection and reports on mapped columns.
        """
        url = f"https://api.notion.com/v1/databases/{self.database_id}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            self._get_property_names()
            found = list(self.prop_map.values())
            return True, f"Connection Successful! Found columns: {', '.join(found)}"
        else:
            return False, f"Connection Failed: {response.text}"

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
