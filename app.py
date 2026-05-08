import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_fetcher import get_nifty500_stocks, get_stock_fundamentals, get_price_data, get_sector_data
from fundamental_analysis import filter_fundamentals, get_holding_category
from technical_analysis import calculate_ema, is_cup_and_handle, is_range_breakout, is_tight_setup
from sector_mapping import get_sector_index
import time

def create_chart(df, symbol, timeframe="Daily"):
    if df.empty:
        return None

    fig = go.Figure(data=[go.Candlestick(x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Price')])

    # Add EMAs
    for ema_name in ['EMA10', 'EMA20', 'EMA50', 'EMA200']:
        if ema_name in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[ema_name], name=ema_name, line=dict(width=1)))

    fig.update_layout(title=f"{symbol} - {timeframe}", xaxis_rangeslider_visible=False, height=400)
    return fig

FUNDAMENTALS_FILE = "nifty500_fundamentals.csv"

def fetch_and_save_fundamentals():
    nifty500 = get_nifty500_stocks()
    all_data = []

    progress_text = "Refreshing all fundamentals... This will take a few minutes."
    my_bar = st.progress(0, text=progress_text)

    total = len(nifty500)
    for i, (idx, row) in enumerate(nifty500.iterrows()):
        symbol = row['Symbol']
        my_bar.progress((i + 1) / total, text=f"Fetching {symbol} ({i+1}/{total})")

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

    if st.sidebar.button("Refresh Fundamental Data"):
        fetch_and_save_fundamentals()
        st.rerun()

    # Apply filters to the table
    filtered_df = fundamentals_df[
        (fundamentals_df['ROE (%)'] >= roe_filter) &
        (fundamentals_df['ROCE (%)'] >= roce_filter)
    ]

    if selected_industries:
        filtered_df = filtered_df[filtered_df['Industry'].isin(selected_industries)]

    if selected_cat != "Any":
        filtered_df = filtered_df[filtered_df['Category'] == selected_cat]

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Data Table", "🔍 Technical Scanner", "📈 Stock Research"])

    with tab1:
        st.subheader("Nifty 500 Fundamental Overview")
        st.write(f"Showing {len(filtered_df)} stocks matching filters.")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)

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

                    col1, col2 = st.columns(2)
                    with col1:
                        chart_daily = create_chart(df_daily, search_symbol, "Daily")
                        if chart_daily: st.plotly_chart(chart_daily, use_container_width=True)
                    with col2:
                        chart_weekly = create_chart(df_weekly, search_symbol, "Weekly")
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

                for i, row in filtered_df.iterrows():
                    symbol = row['Symbol']
                    industry = row['Industry']

                    progress_bar.progress((i + 1) / total_stocks, text=f"Analyzing {symbol} ({i+1}/{total_stocks})")

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

                    # Pattern detection
                    for p_name, p_func in [("Cup and Handle", is_cup_and_handle), ("Range Breakout", is_range_breakout)]:
                        if p_name in selected_patterns:
                            found = False
                            if timeframe_option in ["Daily", "Both"] and not df_daily.empty:
                                if p_func(df_daily): found = True
                            if not found and timeframe_option in ["Weekly", "Both"] and not df_weekly.empty:
                                if p_func(df_weekly): found = True
                            if found: patterns_found.append(p_name)

                    if "Tight Setup" in selected_patterns:
                        found = False
                        sector_symbol = get_sector_index(industry)
                        if timeframe_option in ["Daily", "Both"] and not df_daily.empty:
                            if sector_symbol not in sector_cache:
                                sector_cache[sector_symbol] = get_sector_data(sector_symbol, interval="1d")
                            if is_tight_setup(df_daily, sector_cache[sector_symbol]):
                                found = True

                        if not found and timeframe_option in ["Weekly", "Both"] and not df_weekly.empty:
                            sector_key_wk = sector_symbol + "_wk"
                            if sector_key_wk not in sector_cache:
                                sector_cache[sector_key_wk] = get_sector_data(sector_symbol, interval="1wk")
                            if is_tight_setup(df_weekly, sector_cache[sector_key_wk]):
                                found = True

                        if found:
                            patterns_found.append("Tight Setup")

                    if patterns_found:
                        results.append({
                            'Symbol': symbol,
                            'Industry': industry,
                            'Category': row['Category'],
                            'Patterns': ", ".join(patterns_found),
                            'ROE': row['ROE (%)'],
                            'ROCE': row['ROCE (%)'],
                            'df_daily': df_daily,
                            'df_weekly': df_weekly
                        })

                    time.sleep(0.05)

                status.update(label="Analysis complete!", state="complete", expanded=False)

            if not results:
                st.warning("No stocks found matching the criteria.")
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
                                        chart_daily = create_chart(res['df_daily'], res['Symbol'], "Daily")
                                        if chart_daily: st.plotly_chart(chart_daily, use_container_width=True)
                                    else:
                                        st.write("Daily chart not available (filtered out)")
                                with col2:
                                    if not res['df_weekly'].empty:
                                        chart_weekly = create_chart(res['df_weekly'], res['Symbol'], "Weekly")
                                        if chart_weekly: st.plotly_chart(chart_weekly, use_container_width=True)
                                    else:
                                        st.write("Weekly chart not available (filtered out)")

if __name__ == "__main__":
    main()
