import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data_fetcher import get_nifty500_stocks, get_stock_fundamentals, get_price_data, get_sector_data
from fundamental_analysis import filter_fundamentals, get_holding_category
from technical_analysis import calculate_ema, is_cup_and_handle, is_range_breakout, is_tight_setup
from sector_mapping import get_sector_index
import time

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
                'Category': category
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
        # Calculate Category if not present
        if 'Category' not in df.columns:
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

    # Sidebar for filters
    st.sidebar.header("Global Filters")
    roe_filter = st.sidebar.slider("Minimum ROE (%)", 0, 100, 15)
    roce_filter = st.sidebar.slider("Minimum ROCE (%)", 0, 100, 15)

    industries = sorted(fundamentals_df['Industry'].unique().tolist())
    selected_industries = st.sidebar.multiselect("Industries", industries, default=[])

    cat_options = ["Any", "FII", "DII", "Both"]
    selected_cat = st.sidebar.selectbox("FII/DII Increase Category", cat_options)

    st.sidebar.markdown("---")
    st.sidebar.header("Technical Analysis Settings")
    pattern_options = ["Cup and Handle", "Range Breakout", "Tight Setup"]
    selected_patterns = st.sidebar.multiselect("Select Patterns", pattern_options, default=pattern_options)
    timeframe_option = st.sidebar.radio("Pattern Timeframe", ["Daily", "Weekly", "Both"], index=0)

    breakout_mode = st.sidebar.radio("Breakout Status", ["Both", "Already Broken", "On the Verge"], index=0)

    col_ref1, col_ref2 = st.sidebar.columns(2)
    if col_ref1.button("Resume Fetch"):
        fetch_and_save_fundamentals()
        st.rerun()
    if col_ref2.button("Full Refresh"):
        import os
        if os.path.exists(FUNDAMENTALS_FILE):
            os.remove(FUNDAMENTALS_FILE)
        fetch_and_save_fundamentals()
        st.rerun()

    if st.sidebar.button("Refresh Nifty 500 List"):
        get_nifty500_stocks(refresh=True)
        st.success("Nifty 500 list updated!")

    # Apply filters to the table
    filtered_df = fundamentals_df[
        (fundamentals_df['ROE (%)'] >= roe_filter) &
        (fundamentals_df['ROCE (%)'] >= roce_filter)
    ]

    if selected_industries:
        filtered_df = filtered_df[filtered_df['Industry'].isin(selected_industries)]

    if selected_cat != "Any":
        filtered_df = filtered_df[filtered_df['Category'] == selected_cat]
    else:
        # If "Any" is selected, we still only want those that have at least one increase
        filtered_df = filtered_df[filtered_df['Category'] != "None"]

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Data Table", "🔍 Technical Scanner", "📈 Stock Research"])

    with tab1:
        st.subheader("Nifty 500 Fundamental Overview")
        st.info("Showing stocks where FII or DII holdings increased in back-to-back 2 quarters.")

        view_mode = st.radio("View Mode", ["Table", "Charts"], horizontal=True)

        if view_mode == "Table":
            st.write(f"Showing {len(filtered_df)} stocks matching filters.")
            st.dataframe(filtered_df, use_container_width=True, hide_index=True)
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
                    period = "1y" if chart_timeframe == "Daily" else "2y"

                    df_price = get_price_data(symbol, period=period, interval=interval)
                    if not df_price.empty:
                        df_price = calculate_ema(df_price)
                        fig = create_chart(df_price, symbol, chart_timeframe)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.error(f"Failed to fetch data for {symbol}")
                    st.divider()

    with tab3:
        search_symbol = st.text_input("Search Stock (e.g., RELIANCE, TCS)", "").upper().strip()
        if search_symbol:
            st.subheader(f"Search Result: {search_symbol}")
            with st.spinner(f"Fetching data for {search_symbol}..."):
                df_daily = get_price_data(search_symbol, period="1y", interval="1d")
                df_weekly = get_price_data(search_symbol, period="2y", interval="1wk")

                if not df_daily.empty:
                    df_daily = calculate_ema(df_daily)
                    df_weekly = calculate_ema(df_weekly)

                    # Also scan for patterns in the search tab
                    regs_daily = []
                    regs_weekly = []
                    patterns = []

                    for p_name, p_func in [("Cup and Handle", is_cup_and_handle), ("Range Breakout", is_range_breakout)]:
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
                        if chart_daily: st.plotly_chart(chart_daily, use_container_width=True)
                    with col2:
                        chart_weekly = create_chart(df_weekly, search_symbol, "Weekly", regions=regs_weekly)
                        if chart_weekly: st.plotly_chart(chart_weekly, use_container_width=True)

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
                        df_daily = get_price_data(symbol, period="1y", interval="1d")
                        if not df_daily.empty: df_daily = calculate_ema(df_daily)

                    if timeframe_option in ["Weekly", "Both"]:
                        df_weekly = get_price_data(symbol, period="2y", interval="1wk")
                        if not df_weekly.empty: df_weekly = calculate_ema(df_weekly)

                    patterns_found = []
                    regions_daily = []
                    regions_weekly = []

                    # Pattern detection
                    for p_name, p_func in [("Cup and Handle", is_cup_and_handle), ("Range Breakout", is_range_breakout)]:
                        if p_name in selected_patterns:
                            found_daily = False
                            found_weekly = False
                            if timeframe_option in ["Daily", "Both"] and not df_daily.empty:
                                found_daily, reg = p_func(df_daily)
                                if found_daily: regions_daily.append(reg)
                            if timeframe_option in ["Weekly", "Both"] and not df_weekly.empty:
                                found_weekly, reg = p_func(df_weekly)
                                if found_weekly: regions_weekly.append(reg)
                            if found_daily or found_weekly: patterns_found.append(p_name)

                    if "Tight Setup" in selected_patterns:
                        found_daily = False
                        found_weekly = False
                        sector_symbol = get_sector_index(industry)
                        if timeframe_option in ["Daily", "Both"] and not df_daily.empty:
                            if sector_symbol not in sector_cache:
                                sector_cache[sector_symbol] = get_sector_data(sector_symbol, interval="1d")
                            found_daily, reg = is_tight_setup(df_daily, sector_cache[sector_symbol])
                            if found_daily: regions_daily.append(reg)

                        if timeframe_option in ["Weekly", "Both"] and not df_weekly.empty:
                            sector_key_wk = sector_symbol + "_wk"
                            if sector_key_wk not in sector_cache:
                                sector_cache[sector_key_wk] = get_sector_data(sector_symbol, interval="1wk")
                            found_weekly, reg = is_tight_setup(df_weekly, sector_cache[sector_key_wk])
                            if found_weekly: regions_weekly.append(reg)

                        if found_daily or found_weekly:
                            patterns_found.append("Tight Setup")

                    # Final filtering based on breakout mode
                    if breakout_mode != "Both":
                        all_regions = regions_daily + regions_weekly
                        has_broken = any(r.get('status') == 'Broken' for r in all_regions)
                        has_verge = any(r.get('status') == 'Verge' for r in all_regions)

                        # Tight Setup is always considered "Active" but doesn't have broken/verge status
                        # If user specifically wants breakouts, and it's ONLY tight setup, we might skip?
                        # Let's assume Tight Setup is neutral and doesn't interfere.

                        if breakout_mode == "Already Broken" and not has_broken:
                            patterns_found = [p for p in patterns_found if p == "Tight Setup"]
                        elif breakout_mode == "On the Verge" and not has_verge:
                            patterns_found = [p for p in patterns_found if p == "Tight Setup"]

                    if not patterns_found:
                        continue

                    if patterns_found:
                        results.append({
                            'Symbol': symbol,
                            'Industry': industry,
                            'Category': row['Category'],
                            'Patterns': ", ".join(patterns_found),
                            'ROE': row['ROE (%)'],
                            'ROCE': row['ROCE (%)'],
                            'df_daily': df_daily,
                            'df_weekly': df_weekly,
                            'regions_daily': regions_daily,
                            'regions_weekly': regions_weekly
                        })

                    time.sleep(0.05)

                status.update(label="Analysis complete!", state="complete", expanded=False)

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
                            with st.expander(f"{res['Symbol']} - {res['Patterns']} (ROE: {res['ROE']}%, ROCE: {res['ROCE']}%)"):
                                col1, col2 = st.columns(2)
                                with col1:
                                    if not res['df_daily'].empty:
                                        chart_daily = create_chart(res['df_daily'], res['Symbol'], "Daily", regions=res['regions_daily'])
                                        if chart_daily: st.plotly_chart(chart_daily, use_container_width=True)
                                    else:
                                        st.write("Daily chart not available (filtered out)")
                                with col2:
                                    if not res['df_weekly'].empty:
                                        chart_weekly = create_chart(res['df_weekly'], res['Symbol'], "Weekly", regions=res['regions_weekly'])
                                        if chart_weekly: st.plotly_chart(chart_weekly, use_container_width=True)
                                    else:
                                        st.write("Weekly chart not available (filtered out)")

if __name__ == "__main__":
    main()
