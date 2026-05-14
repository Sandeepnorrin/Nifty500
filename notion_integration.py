import requests
import json
from datetime import datetime

class NotionSync:
    def __init__(self, api_key, database_id):
        self.api_key = api_key.strip()
        self.database_id = self._extract_id(database_id)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        self.prop_map = {}

    def _extract_id(self, db_input):
        """Extracts the 32-character ID from a Notion URL if provided."""
        db_input = db_input.strip()
        if "/" in db_input:
            # Handle URL like https://www.notion.so/360f8ac4f6cb8065bbc1e38a22eda951?v=...
            # The ID is the part after the last / and before ?
            part = db_input.split("/")[-1].split("?")[0]
            if len(part) >= 32:
                return part[:32]
        return db_input

    def _get_property_names(self):
        """
        Fetches database metadata to map internal keys to actual property names and types.
        """
        url = f"https://api.notion.com/v1/databases/{self.database_id}"
        print(f"DEBUG: Fetching database metadata from {url}")
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            data = response.json()
            props = data.get("properties", {})

            # Map based on best match
            mapping = {}
            for n, meta in props.items():
                low = n.lower().replace("_", " ").strip()
                p_type = meta.get('type')

                info = {'name': n, 'type': p_type}

                if "stock" in low: mapping['stock'] = info
                elif "breakout" in low and "type" in low: mapping['type'] = info
                elif "breakout" in low and "price" in low: mapping['price'] = info
                elif "cmp" in low or ("current" in low and "price" in low): mapping['cmp'] = info
                elif "broken" in low: mapping['broken'] = info
                elif "15%" in low or "target" in low: mapping['target'] = info
                elif "date" in low: mapping['date'] = info
                elif "timeframe" in low: mapping['timeframe'] = info

            self.prop_map = mapping
            print(f"DEBUG: Property mapping result: {self.prop_map}")
            return True
        else:
            error_msg = f"Failed to fetch Notion database metadata. Status: {response.status_code}, Body: {response.text}"
            print(f"DEBUG: {error_msg}")
            if response.status_code == 404:
                raise Exception("Notion Error: Database not found (404). Please check the Database ID and ensure the Integration is shared with the database.")
            elif response.status_code == 401:
                raise Exception("Notion Error: Unauthorized (401). Please check your API Key.")
            else:
                raise Exception(error_msg)

    def query_stock(self, stock_name, breakout_price):
        """
        Queries the database for an existing record with the same stock name and breakout price.
        """
        if not self.prop_map:
            self._get_property_names()

        stock_info = self.prop_map.get('stock')
        price_info = self.prop_map.get('price')

        if not stock_info or not price_info:
            print(f"DEBUG: Missing essential mappings for query. Stock: {stock_info}, Price: {price_info}")
            return None

        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"

        # Determine filter type for stock (usually title)
        stock_filter = {"title": {"equals": stock_name}}
        if stock_info['type'] == 'rich_text':
             stock_filter = {"rich_text": {"equals": stock_name}}

        filter_data = {
            "filter": {
                "and": [
                    {
                        "property": stock_info['name'],
                        **stock_filter
                    },
                    {
                        "property": price_info['name'],
                        "number": {
                            "equals": round(float(breakout_price), 2)
                        }
                    }
                ]
            }
        }

        print(f"DEBUG: Querying stock {stock_name} with price {breakout_price}")
        response = requests.post(url, headers=self.headers, json=filter_data)
        if response.status_code == 200:
            results = response.json().get("results", [])
            print(f"DEBUG: Query successful. Found {len(results)} matches.")
            return results[0] if results else None
        else:
            error_text = response.text
            print(f"DEBUG: Error querying Notion: Status {response.status_code}, Body: {error_text}")
            raise Exception(f"Notion API Error (Status {response.status_code}): {error_text}")

    def create_record(self, data):
        """
        Creates a new record in the Notion database.
        data: dict containing stock info
        """
        if not self.prop_map:
            self._get_property_names()

        url = "https://api.notion.com/v1/pages"

        properties = {}

        def set_prop(key, value):
            if key not in self.prop_map: return
            info = self.prop_map[key]
            name = info['name']
            p_type = info['type']

            if p_type == 'title': properties[name] = {"title": [{"text": {"content": str(value)}}]}
            elif p_type == 'rich_text': properties[name] = {"rich_text": [{"text": {"content": str(value)}}]}
            elif p_type == 'number': properties[name] = {"number": round(float(value), 2)}
            elif p_type == 'select': properties[name] = {"select": {"name": str(value)[:100]}}
            elif p_type == 'checkbox': properties[name] = {"checkbox": bool(value)}
            elif p_type == 'date': properties[name] = {"date": {"start": value}}

        set_prop('stock', data['symbol'])
        set_prop('type', data['patterns'])
        set_prop('price', data['breakout_price'])
        set_prop('cmp', data['current_price'])
        set_prop('broken', data['is_broken'])
        set_prop('target', data['is_target_met'])
        set_prop('date', datetime.now().strftime("%Y-%m-%d"))
        set_prop('timeframe', data.get('timeframe', ''))

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties
        }

        print(f"DEBUG: Creating record for {data['symbol']}")
        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code != 200:
             print(f"DEBUG: Create Error. Status: {response.status_code}, Body: {response.text}")
             raise Exception(f"Notion Create Error (Status {response.status_code}): {response.text}")
        print(f"DEBUG: Successfully created record for {data['symbol']}")
        return True

    def update_record(self, page_id, data):
        """
        Updates an existing record in Notion.
        """
        if not self.prop_map:
            self._get_property_names()

        url = f"https://api.notion.com/v1/pages/{page_id}"

        properties = {}

        def set_prop(key, value):
            if key not in self.prop_map: return
            info = self.prop_map[key]
            name = info['name']
            p_type = info['type']

            if p_type == 'number': properties[name] = {"number": round(float(value), 2)}
            elif p_type == 'checkbox': properties[name] = {"checkbox": bool(value)}

        set_prop('cmp', data['current_price'])
        set_prop('broken', data['is_broken'])
        set_prop('target', data['is_target_met'])

        payload = {"properties": properties}
        response = requests.patch(url, headers=self.headers, json=payload)
        if response.status_code != 200:
             raise Exception(f"Notion Update Error: {response.text}")
        return True

    def test_connection(self):
        """
        Tests the connection and reports on mapped columns.
        """
        try:
            self._get_property_names()
            found = [f"{v['name']} ({v['type']})" for v in self.prop_map.values()]
            return True, f"Connection Successful! Mapped columns: {', '.join(found)}"
        except Exception as e:
            return False, f"Connection Failed: {str(e)}"

    def sync_stocks(self, stocks_list):
        """
        Main entry point to sync a list of stocks to Notion.
        stocks_list: list of dicts with keys: symbol, patterns, breakout_price, current_price
        Returns: (created_count, updated_count)
        """
        if not stocks_list:
            print("DEBUG: No stocks to sync.")
            return 0, 0

        created_count = 0
        updated_count = 0
        for stock in stocks_list:
            print(f"DEBUG: Processing sync for {stock['symbol']}")
            # Basic validation
            if not stock.get('breakout_price') or stock.get('breakout_price') <= 0:
                continue

            # Logic for flags
            is_broken = stock['current_price'] > stock['breakout_price']
            is_target_met = stock['current_price'] >= (stock['breakout_price'] * 1.15)

            stock['is_broken'] = is_broken
            stock['is_target_met'] = is_target_met

            try:
                existing = self.query_stock(stock['symbol'], stock['breakout_price'])
                if existing:
                    if self.update_record(existing['id'], stock):
                        updated_count += 1
                else:
                    if self.create_record(stock):
                        created_count += 1
            except Exception as e:
                print(f"ERROR: Sync failed for {stock['symbol']}: {str(e)}")
                # We continue with other stocks

        return created_count, updated_count
