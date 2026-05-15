import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data_fetcher import get_nifty500_stocks, get_stock_fundamentals, get_price_data, get_sector_data
from fundamental_analysis import filter_fundamentals, get_holding_category
from technical_analysis import calculate_ema, is_cup_and_handle, is_range_breakout, is_tight_setup, is_ema_aligned, is_52w_high_breakout
from sector_mapping import get_sector_index
from notion_integration import NotionSync
import time
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

def create_chart(df, symbol, timeframe="Daily", regions=None):
    if df.empty:
        return None

    # Create subplots: row 1 for Candlestick, row 2 for Volume
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, subplot_titles=(f'{symbol} - {timeframe}', 'Volume'),
                        row_width=[0.2, 0.7])

    # Candlestick chart
    fig.add_trace(go.Candlestick(x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Price'), row=1, col=1)

    # Focus on current period (last 1 year for daily, last 2 years for weekly)
    if not df.empty:
        last_date = df.index[-1]
        if timeframe == "Daily":
            start_date = last_date - pd.DateOffset(years=1)
        else:
            start_date = last_date - pd.DateOffset(years=2)
        fig.update_xaxes(range=[start_date, last_date], row=1, col=1)
        fig.update_xaxes(range=[start_date, last_date], row=2, col=1)

        # Auto-scale Y-axis based on visible price range
        visible_df = df[df.index >= start_date]
        if not visible_df.empty:
            y_min = visible_df['Low'].min() * 0.95
            y_max = visible_df['High'].max() * 1.05
            fig.update_yaxes(range=[y_min, y_max], row=1, col=1)

    # Add EMAs
    for ema_name in ['EMA10', 'EMA20', 'EMA50', 'EMA200']:
        if ema_name in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[ema_name], name=ema_name, line=dict(width=1)), row=1, col=1)

    # Volume chart
    colors = ['red' if row['Open'] > row['Close'] else 'green' for index, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Volume', marker_color=colors), row=2, col=1)

    # Add highlights for patterns
    if regions:
        for region in regions:
            color = "blue"
            if region.get('status') == 'Verge':
                color = "orange"

            fig.add_vrect(
                x0=region['start'], x1=region['end'],
                fillcolor=color, opacity=0.2,
                layer="below", line_width=0,
                annotation_text=region['label'],
                annotation_position="top left",
                row=1, col=1
            )

            # Add horizontal line for breakout price
            b_price = region.get('breakout_price')
            if b_price:
                fig.add_shape(
                    type="line",
                    x0=region['start'], x1=df.index[-1],
                    y0=b_price, y1=b_price,
                    line=dict(color=color, width=2, dash="dash"),
                    row=1, col=1
                )

    fig.update_layout(xaxis_rangeslider_visible=False, height=600, showlegend=False)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

    return fig

FUNDAMENTALS_FILE = "nifty500_fundamentals.csv"

def fetch_and_save_fundamentals():
    nifty500 = get_nifty500_stocks()
    all_data = []

    progress_text = "Refreshing all fundamentals... This will take a few minutes."
    my_bar = st.progress(0, text=progress_text)

    total = len(nifty500)

    # Try to load existing data to resume if possible
    try:
        existing_df = pd.read_csv(FUNDAMENTALS_FILE)
        processed_symbols = set(existing_df['Symbol'].tolist())
        all_data = existing_df.to_dict('records')
    except:
        processed_symbols = set()
        all_data = []

    for i, (idx, row) in enumerate(nifty500.iterrows()):
        symbol = row['Symbol']

        # Calculate progress correctly based on the iteration index 'i'
        my_bar.progress((i + 1) / total, text=f"Fetching {symbol} ({i+1}/{total})")

        if symbol in processed_symbols:
            continue

        funds = get_stock_fundamentals(symbol)
        if funds:
            fii = funds.get('FII_Holdings', [])
            dii = funds.get('DII_Holdings', [])

            # Fill with 0 if fewer than 4 quarters
            fii = ([0.0] * (4 - len(fii))) + fii
            dii = ([0.0] * (4 - len(dii))) + dii

            category = get_holding_category(fii, dii)

            # Calculate combined change (Current - Previous Quarter)
            # fii: [Q-3, Q-2, Q-1, Curr]
            fii_change = fii[3] - fii[2]
            dii_change = dii[3] - dii[2]
            comb_change = fii_change + dii_change

            # Also get 52-week high info
            df_3y = get_price_data(symbol, period="3y")
            high_52w = 0.0
            curr_price = 0.0
            pct_from_high = 100.0

            if not df_3y.empty:
                # 52 weeks is approx 252 trading days
                df_1y = df_3y.tail(252)
                high_52w = df_1y['High'].max()
                curr_price = df_1y['Close'].iloc[-1]
                if high_52w > 0:
                    pct_from_high = abs(high_52w - curr_price) / high_52w * 100

            all_data.append({
                'Symbol': symbol,
                'Industry': row['Industry'],
                'ROE (%)': funds.get('ROE') or 0.0,
                'ROCE (%)': funds.get('ROCE') or 0.0,
                'FII Q-3': fii[0],
                'FII Q-2': fii[1],
                'FII Q-1': fii[2],
                'FII Curr': fii[3],
                'DII Q-3': dii[0],
                'DII Q-2': dii[1],
                'DII Q-1': dii[2],
                'DII Curr': dii[3],
                'Category': category,
                'Combined Change (%)': round(float(comb_change), 2),
                'Market Cap (Cr)': funds.get('Market Cap') or 0.0,
                '52W High': round(float(high_52w), 2),
                'Current Price': round(float(curr_price), 2),
                '% From 52W High': round(float(pct_from_high), 2)
            })

        # Periodic save to avoid losing all progress on error
        if len(all_data) % 20 == 0:
            pd.DataFrame(all_data).to_csv(FUNDAMENTALS_FILE, index=False)

        time.sleep(0.05)

    my_bar.empty()
    df = pd.DataFrame(all_data)
    df.to_csv(FUNDAMENTALS_FILE, index=False)
    return df

def load_fundamentals():
    try:
        df = pd.read_csv(FUNDAMENTALS_FILE)

        # Assign Market Cap Categories based on Nifty 500 rules:
        # Top 100: Large, 101-250: Mid, 251-500: Small
        if 'Market Cap (Cr)' in df.columns:
            # Sort by Market Cap descending and assign rank
            df = df.sort_values(by='Market Cap (Cr)', ascending=False)
            df['Rank'] = range(1, len(df) + 1)

            def get_mcap_cat(rank):
                if rank <= 100: return 'Large'
                elif rank <= 250: return 'Mid'
                return 'Small'

            df['Market Cap Cat'] = df['Rank'].apply(get_mcap_cat)
            df = df.drop(columns=['Rank'])

        if 'Combined Change (%)' in df.columns:
            def get_change_bucket(val):
                if val <= 1.5: return '<= 1.5%'
                elif 1.5 < val <= 3.0: return '1.5% - 3%'
                elif 3.0 < val <= 7.0: return '3% - 7%'
                elif 7.0 < val <= 10.0: return '7% - 10%'
                return '> 10%'
            df['Change Bucket'] = df['Combined Change (%)'].apply(get_change_bucket)

        # Check if new columns exist, if not, we might need a refresh
        required_cols = ['52W High', 'Current Price', '% From 52W High', 'Market Cap (Cr)', 'Combined Change (%)']
        if not all(col in df.columns for col in required_cols) or 'Category' not in df.columns:
            st.warning("Fundamentals data is outdated. Please click 'Full Refresh' to update all columns.")

            # Still try to calculate Category if only that is missing
            if 'Category' not in df.columns and all(c in df.columns for c in ['FII Curr', 'DII Curr']):
                 df['Category'] = df.apply(lambda row: get_holding_category(
                    [row['FII Q-3'], row['FII Q-2'], row['FII Q-1'], row['FII Curr']],
                    [row['DII Q-3'], row['DII Q-2'], row['DII Q-1'], row['DII Curr']]
                ), axis=1)
                 df.to_csv(FUNDAMENTALS_FILE, index=False)
        return df
    except FileNotFoundError:
        return fetch_and_save_fundamentals()

def main():
    st.set_page_config(page_title="Nifty 500 Stock Analyzer", layout="wide")
    st.title("📈 Nifty 500 Stock Analyzer")

    # Load fundamentals first to populate filters
    fundamentals_df = load_fundamentals()

    # Notion Settings in Sidebar
    st.sidebar.header("📝 Notion Settings")

    # Load defaults from environment variables
    default_key = os.environ.get("NOTION_API_KEY", "")
    default_db_id = os.environ.get("NOTION_DATABASE_ID", "360f8ac4f6cb8065bbc1e38a22eda951")

    notion_api_key = st.sidebar.text_input("Notion API Key", value=default_key, type="password")
    notion_db_id = st.sidebar.text_input("Notion Database ID", value=default_db_id)
    enable_notion = st.sidebar.checkbox("Enable Notion Sync", value=True)

    if st.sidebar.button("🔌 Test Notion Connection"):
        if not notion_api_key or not notion_db_id:
            st.sidebar.error("Please provide both API Key and Database ID")
        else:
            with st.sidebar:
                with st.spinner("Testing..."):
                    notion = NotionSync(notion_api_key, notion_db_id)
                    success, msg = notion.test_connection()
                    if success:
                        st.success(msg)
                        if "stock" not in notion.prop_map or "price" not in notion.prop_map:
                             st.warning("⚠️ 'Stock Name' or 'Breakout Price' columns not detected. Sync might fail.")
                    else:
                        st.error(msg)
                        if "404" in msg or "Database not found" in msg:
                            st.info("💡 **Tip:** Notion returned 404. Check your DB ID (32 chars) and ensure you have 'Connected' the Integration to the database in Notion.")

    # Top Filters
    with st.expander("🛠️ Global Filters & Settings", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            roe_filter = st.slider("Minimum ROE (%)", 0, 100, 15)
            roce_filter = st.slider("Minimum ROCE (%)", 0, 100, 15)
        with col2:
            industries = sorted(fundamentals_df['Industry'].unique().tolist())
            selected_industries = st.multiselect("Industries", industries, default=[])
            mcap_options = ["Large", "Mid", "Small"]
            selected_mcap = st.multiselect("Market Cap", mcap_options, default=mcap_options)
            cat_options = ["Any", "FII", "DII", "Both"]
            selected_cat = st.selectbox("FII/DII Increase Category", cat_options)
        with col3:
            high_filter = st.slider("Max % Away from 52W High", 0, 100, 20)
            change_options = ["<= 1.5%", "1.5% - 3%", "3% - 7%", "7% - 10%", "> 10%"]
            selected_change = st.multiselect("Combined Holding Change", change_options, default=change_options)
            pattern_options = ["Cup and Handle", "Range Breakout", "Tight Setup", "52W High Breakout"]
            selected_patterns = st.multiselect("Select Patterns", pattern_options, default=pattern_options)
        with col4:
            timeframe_option = st.radio("Pattern Timeframe", ["Daily", "Weekly", "Both"], index=0, horizontal=True)
            breakout_mode = st.radio("Breakout Status", ["On the Verge", "Already Broken", "Both"], index=0, horizontal=True)
            dist_filter = st.slider("Max % from Breakout Price", 0, 100, 5)
            ema_filter = st.selectbox("EMA Alignment (20>50>200)", ["All", "Yes", "No"], index=0)

        col_btn1, col_btn2, col_btn3, _ = st.columns([1, 1, 1, 5])
        if col_btn1.button("Resume Fetch"):
            fetch_and_save_fundamentals()
            st.rerun()
        if col_btn2.button("Full Refresh"):
            if os.path.exists(FUNDAMENTALS_FILE):
                os.remove(FUNDAMENTALS_FILE)
            fetch_and_save_fundamentals()
            st.rerun()
        if col_btn3.button("Update Nifty 500"):
            get_nifty500_stocks(refresh=True)
            st.success("List updated!")

    # Apply filters to the table
    filtered_df = fundamentals_df[
        (fundamentals_df['ROE (%)'] >= roe_filter) &
        (fundamentals_df['ROCE (%)'] >= roce_filter)
    ]

    if '% From 52W High' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['% From 52W High'] <= high_filter]

    if selected_industries:
        filtered_df = filtered_df[filtered_df['Industry'].isin(selected_industries)]

    if 'Market Cap Cat' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Market Cap Cat'].isin(selected_mcap)]

    if 'Change Bucket' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Change Bucket'].isin(selected_change)]

    if selected_cat != "Any":
        filtered_df = filtered_df[filtered_df['Category'] == selected_cat]
    else:
        # If "Any" is selected, we still only want those that have at least one increase
        filtered_df = filtered_df[filtered_df['Category'] != "None"]

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Data Table", "🔍 Technical Scanner", "📈 Stock Research"])

    with tab1:
        st.subheader("Nifty 500 Fundamental Overview")
        st.info("Showing stocks where FII or DII holdings increased in back-to-back 2 quarters. Change is (Curr FII - Prev FII) + (Curr DII - Prev DII).")

        view_mode = st.radio("View Mode", ["Table", "Charts"], horizontal=True)

        if view_mode == "Table":
            st.write(f"Showing {len(filtered_df)} stocks matching filters.")

            # Logical column reordering
            cols = filtered_df.columns.tolist()
            desired_order = [
                'Symbol', 'Industry', 'Current Price', 'Market Cap (Cr)', 'Market Cap Cat',
                'ROE (%)', 'ROCE (%)', '% From 52W High', 'Combined Change (%)', 'Change Bucket',
                'Category', 'FII Curr', 'FII Q-1', 'FII Q-2', 'FII Q-3',
                'DII Curr', 'DII Q-1', 'DII Q-2', 'DII Q-3'
            ]

            # Use only columns that exist in the dataframe
            final_cols = [c for c in desired_order if c in cols]
            # Add any remaining columns
            final_cols += [c for c in cols if c not in final_cols]

            st.dataframe(filtered_df[final_cols], width="stretch", hide_index=True)
        else:
            chart_timeframe = st.selectbox("Chart Timeframe", ["Daily", "Weekly"], key="tab1_timeframe")
            st.write(f"Displaying charts for {len(filtered_df)} stocks.")

            # Limit display to avoid crashing browser if many stocks are filtered
            max_charts = 20
            stocks_to_show = filtered_df.head(max_charts)
            if len(filtered_df) > max_charts:
                st.warning(f"Showing first {max_charts} stocks. Refine filters to see others.")

            for _, row in stocks_to_show.iterrows():
                symbol = row['Symbol']
                with st.container():
                    st.markdown(f"### {symbol} ({row['Industry']})")
                    st.write(f"ROE: {row['ROE (%)']}%, ROCE: {row['ROCE (%)']}%, Category: {row['Category']}")

                    interval = "1d" if chart_timeframe == "Daily" else "1wk"
                    period = "3y"

                    df_price = get_price_data(symbol, period=period, interval=interval)
                    if not df_price.empty:
                        df_price = calculate_ema(df_price)
                        fig = create_chart(df_price, symbol, chart_timeframe)
                        st.plotly_chart(fig, width="stretch")
                    else:
                        st.error(f"Failed to fetch data for {symbol}")
                    st.divider()

    with tab3:
        search_symbol = st.text_input("Search Stock (e.g., RELIANCE, TCS)", "").upper().strip()
        if search_symbol:
            st.subheader(f"Search Result: {search_symbol}")
            with st.spinner(f"Fetching data for {search_symbol}..."):
                df_daily = get_price_data(search_symbol, period="3y", interval="1d")
                df_weekly = get_price_data(search_symbol, period="3y", interval="1wk")

                if not df_daily.empty:
                    df_daily = calculate_ema(df_daily)
                    df_weekly = calculate_ema(df_weekly)

                    # Also scan for patterns in the search tab
                    regs_daily = []
                    regs_weekly = []
                    patterns = []

                    strategies_search = [
                        ("Cup and Handle", is_cup_and_handle),
                        ("Range Breakout", is_range_breakout),
                        ("52W High Breakout", is_52w_high_breakout)
                    ]
                    for p_name, p_func in strategies_search:
                        f_d, r_d = p_func(df_daily)
                        if f_d:
                            regs_daily.append(r_d)
                            patterns.append(f"{p_name} (Daily)")
                        f_w, r_w = p_func(df_weekly)
                        if f_w:
                            regs_weekly.append(r_w)
                            patterns.append(f"{p_name} (Weekly)")

                    if patterns:
                        st.success(f"Patterns found: {', '.join(patterns)}")

                    col1, col2 = st.columns(2)
                    with col1:
                        chart_daily = create_chart(df_daily, search_symbol, "Daily", regions=regs_daily)
                        if chart_daily: st.plotly_chart(chart_daily, width="stretch")
                    with col2:
                        chart_weekly = create_chart(df_weekly, search_symbol, "Weekly", regions=regs_weekly)
                        if chart_weekly: st.plotly_chart(chart_weekly, width="stretch")

                    # Also show fundamentals if possible
                    fundamentals = get_stock_fundamentals(search_symbol)
                    if fundamentals:
                        st.write(f"**Fundamentals:** ROE: {fundamentals.get('ROE') or 'N/A'}%, ROCE: {fundamentals.get('ROCE') or 'N/A'}%")
                        fii = fundamentals.get('FII_Holdings', [])
                        dii = fundamentals.get('DII_Holdings', [])
                        st.write(f"**FII Holdings (last 3 qtrs):** {fii}")
                        st.write(f"**DII Holdings (last 3 qtrs):** {dii}")
                else:
                    st.error(f"Could not find data for symbol: {search_symbol}")

    with tab2:
        st.subheader("Pattern Scanner")
        st.write("Scan filtered stocks for selected technical patterns.")

        if st.button("Start Technical Scan"):
            with st.status("Analyzing filtered stocks...", expanded=True) as status:
                if filtered_df.empty:
                    st.warning("No stocks match the criteria.")
                    return

                results = []
                progress_bar = st.progress(0)

                total_stocks = len(filtered_df)
                sector_cache = {}

                for idx, (df_idx, row) in enumerate(filtered_df.iterrows()):
                    symbol = row['Symbol']
                    industry = row['Industry']

                    progress_bar.progress((idx + 1) / total_stocks, text=f"Analyzing {symbol} ({idx+1}/{total_stocks})")

                    # Technical Analysis
                    df_daily = pd.DataFrame()
                    df_weekly = pd.DataFrame()

                    if timeframe_option in ["Daily", "Both"]:
                        df_daily = get_price_data(symbol, period="3y", interval="1d")
                        if not df_daily.empty: df_daily = calculate_ema(df_daily)

                    if timeframe_option in ["Weekly", "Both"]:
                        df_weekly = get_price_data(symbol, period="3y", interval="1wk")
                        if not df_weekly.empty: df_weekly = calculate_ema(df_weekly)

                    patterns_found = []
                    regions_daily = []
                    regions_weekly = []

                    # Track which timeframe matched
                    matched_timeframes = set()

                    # Pattern detection
                    strategies = [
                        ("Cup and Handle", is_cup_and_handle),
                        ("Range Breakout", is_range_breakout),
                        ("52W High Breakout", is_52w_high_breakout)
                    ]
                    for p_name, p_func in strategies:
                        if p_name in selected_patterns:
                            found_daily = False
                            found_weekly = False
                            if timeframe_option in ["Daily", "Both"] and not df_daily.empty:
                                found_daily, reg = p_func(df_daily)
                                if found_daily:
                                    regions_daily.append(reg)
                                    matched_timeframes.add("Daily")
                            if timeframe_option in ["Weekly", "Both"] and not df_weekly.empty:
                                found_weekly, reg = p_func(df_weekly)
                                if found_weekly:
                                    regions_weekly.append(reg)
                                    matched_timeframes.add("Weekly")
                            if found_daily or found_weekly: patterns_found.append(p_name)

                    if "Tight Setup" in selected_patterns:
                        found_daily = False
                        found_weekly = False
                        sector_symbol = get_sector_index(industry)
                        if timeframe_option in ["Daily", "Both"] and not df_daily.empty:
                            if sector_symbol not in sector_cache:
                                sector_cache[sector_symbol] = get_sector_data(sector_symbol, interval="1d")
                            found_daily, reg = is_tight_setup(df_daily, sector_cache[sector_symbol])
                            if found_daily:
                                regions_daily.append(reg)
                                matched_timeframes.add("Daily")

                        if timeframe_option in ["Weekly", "Both"] and not df_weekly.empty:
                            sector_key_wk = sector_symbol + "_wk"
                            if sector_key_wk not in sector_cache:
                                sector_cache[sector_key_wk] = get_sector_data(sector_symbol, interval="1wk")
                            found_weekly, reg = is_tight_setup(df_weekly, sector_cache[sector_key_wk])
                            if found_weekly:
                                regions_weekly.append(reg)
                                matched_timeframes.add("Weekly")

                        if (timeframe_option in ["Daily", "Both"] and found_daily) or \
                           (timeframe_option in ["Weekly", "Both"] and found_weekly):
                            patterns_found.append("Tight Setup")

                    # Final filtering based on breakout mode
                    # EMA Filter check
                    if ema_filter != "All":
                        is_aligned = False
                        if timeframe_option in ["Daily", "Both"] and not df_daily.empty:
                            if is_ema_aligned(df_daily): is_aligned = True
                        if not is_aligned and timeframe_option in ["Weekly", "Both"] and not df_weekly.empty:
                            if is_ema_aligned(df_weekly): is_aligned = True

                        if ema_filter == "Yes" and not is_aligned: continue
                        if ema_filter == "No" and is_aligned: continue

                    # Final filtering based on breakout mode
                    if breakout_mode != "Both":
                        # Filter regions based on status
                        if breakout_mode == "Already Broken":
                            regions_daily = [r for r in regions_daily if r.get('status') == 'Broken']
                            regions_weekly = [r for r in regions_weekly if r.get('status') == 'Broken']
                        elif breakout_mode == "On the Verge":
                            regions_daily = [r for r in regions_daily if r.get('status') == 'Verge']
                            regions_weekly = [r for r in regions_weekly if r.get('status') == 'Verge']

                        # Re-calculate patterns found after filtering regions
                        current_patterns = set()

                        valid_regions_daily = []
                        valid_regions_weekly = []

                        for r in regions_daily:
                            if r.get('status') == 'Broken':
                                b_price = r.get('breakout_price')
                                current_p = df_daily['Close'].iloc[-1] if not df_daily.empty else 0
                                if b_price and b_price > 0 and current_p > 0:
                                    pct_dist = (current_p - b_price) / b_price * 100
                                    if pct_dist > dist_filter: continue
                            current_patterns.add(r['label'].replace(' (Verge)', '').replace(' & Handle', ' and Handle'))
                            valid_regions_daily.append(r)

                        for r in regions_weekly:
                            if r.get('status') == 'Broken':
                                b_price = r.get('breakout_price')
                                current_p = df_weekly['Close'].iloc[-1] if not df_weekly.empty else 0
                                if b_price and b_price > 0 and current_p > 0:
                                    pct_dist = (current_p - b_price) / b_price * 100
                                    if pct_dist > dist_filter: continue
                            current_patterns.add(r['label'].replace(' (Verge)', '').replace(' & Handle', ' and Handle'))
                            valid_regions_weekly.append(r)


                        regions_daily = valid_regions_daily
                        regions_weekly = valid_regions_weekly

                        patterns_found = list(current_patterns)

                    if not patterns_found:
                        continue

                    if patterns_found:
                        # Extract breakout price for Notion (use first found region that has a breakout price)
                        b_price = 0
                        for r in regions_daily + regions_weekly:
                            if r.get('breakout_price', 0) > 0:
                                b_price = r.get('breakout_price')
                                break

                        tf_str = " & ".join(sorted(list(matched_timeframes)))

                        results.append({
                            'Symbol': symbol,
                            'Industry': industry,
                            'Category': row['Category'],
                            'Patterns': ", ".join(patterns_found),
                            'Timeframe': tf_str,
                            'ROE': row['ROE (%)'],
                            'ROCE': row['ROCE (%)'],
                            'Current Price': row['Current Price'],
                            'Breakout Price': b_price,
                            'df_daily': df_daily,
                            'df_weekly': df_weekly,
                            'regions_daily': regions_daily,
                            'regions_weekly': regions_weekly
                        })

                    time.sleep(0.05)

                status.update(label="Analysis complete!", state="complete", expanded=False)

                # Sync to Notion if enabled
                if enable_notion and notion_api_key and notion_db_id and results:
                    st.info("Syncing results to Notion...")
                    notion = NotionSync(notion_api_key, notion_db_id)
                    notion_list = []
                    for r in results:
                        notion_list.append({
                            'symbol': r['Symbol'],
                            'patterns': r['Patterns'], # Send all patterns found
                            'breakout_price': r['Breakout Price'],
                            'current_price': r['Current Price'],
                            'timeframe': r['Timeframe']
                        })

                    try:
                        created, updated = notion.sync_stocks(notion_list)
                        if created > 0 or updated > 0:
                            st.success(f"Notion Sync Complete: {created} records created, {updated} records updated.")
                        else:
                            st.info("Notion Sync: No new or updated records.")
                    except Exception as e:
                        error_msg = str(e)
                        st.error(f"Notion sync failed: {error_msg}")
                        if "object_not_found" in error_msg or "404" in error_msg:
                            st.warning("💡 **Tip:** Notion returned a '404 Object Not Found' error. This usually means the database ID is incorrect or your Integration hasn't been shared with the database. Please go to your Notion Database -> Options (...) -> Connect to -> Select 'Sandeep Norrin stock Tracker'.")

            if not results:
                st.warning("No stocks found matching both Fundamental and Technical criteria.")
                st.info("Try relaxing filters: lower ROE/ROCE, select 'Any' Category, or select all Patterns.")
            else:
                st.subheader(f"Found {len(results)} matching stocks")

                # Group results by category
                for cat in ['Both', 'FII', 'DII']:
                    cat_results = [r for r in results if r['Category'] == cat]
                    if cat_results:
                        st.header(f"Category: {cat} increased holding")
                        for res in cat_results:
                            with st.expander(f"**{res['Symbol']}** | {res['Patterns']} | TF: {res['Timeframe']} | Breakout: {res['Breakout Price']} | CMP: {res['Current Price']}"):
                                st.write(f"**Industry:** {res['Industry']} | **ROE:** {res['ROE']}% | **ROCE:** {res['ROCE']}% | **Institutional Category:** {res['Category']}")
                                col1, col2 = st.columns(2)
                                with col1:
                                    if not res['df_daily'].empty:
                                        chart_daily = create_chart(res['df_daily'], res['Symbol'], "Daily", regions=res['regions_daily'])
                                        if chart_daily: st.plotly_chart(chart_daily, width="stretch")
                                    else:
                                        st.write("Daily chart not available (filtered out)")
                                with col2:
                                    if not res['df_weekly'].empty:
                                        chart_weekly = create_chart(res['df_weekly'], res['Symbol'], "Weekly", regions=res['regions_weekly'])
                                        if chart_weekly: st.plotly_chart(chart_weekly, width="stretch")
                                    else:
                                        st.write("Weekly chart not available (filtered out)")

if __name__ == "__main__":
    main()
