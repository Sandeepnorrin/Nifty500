import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_fetcher import get_nifty500_stocks, get_stock_fundamentals, get_price_data, get_sector_data
from fundamental_analysis import filter_fundamentals
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

@st.cache_data(ttl=86400) # Cache for 24 hours
def fetch_all_fundamentals():
    nifty500 = get_nifty500_stocks()
    all_data = []

    progress_text = "Fetching all fundamentals... This might take some time."
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

            all_data.append({
                'Symbol': symbol,
                'Industry': row['Industry'],
                'ROE (%)': funds.get('ROE'),
                'ROCE (%)': funds.get('ROCE'),
                'FII Q-3': fii[0],
                'FII Q-2': fii[1],
                'FII Q-1': fii[2],
                'FII Curr': fii[3],
                'DII Q-3': dii[0],
                'DII Q-2': dii[1],
                'DII Q-1': dii[2],
                'DII Curr': dii[3]
            })
        time.sleep(0.05)

    my_bar.empty()
    return pd.DataFrame(all_data)

def main():
    st.set_page_config(page_title="Nifty 500 Stock Analyzer", layout="wide")
    st.title("📈 Nifty 500 Stock Analyzer")
    st.write("Analyze Nifty 500 stocks based on fundamental and technical criteria.")

    # Show fundamental table by default
    st.subheader("Nifty 500 Fundamental Overview")
    if st.button("Refresh Fundamental Data"):
        st.cache_data.clear()
        st.rerun()

    fundamentals_df = fetch_all_fundamentals()
    if not fundamentals_df.empty:
        st.dataframe(fundamentals_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch fundamental data.")

    # Sidebar for filters
    st.sidebar.header("Filters")
    roe_filter = st.sidebar.slider("Minimum ROE (%)", 0, 100, 15)
    roce_filter = st.sidebar.slider("Minimum ROCE (%)", 0, 100, 15)

    pattern_options = ["Cup and Handle", "Range Breakout", "Tight Setup"]
    selected_patterns = st.sidebar.multiselect("Select Technical Patterns", pattern_options, default=pattern_options)

    st.sidebar.markdown("---")
    search_symbol = st.sidebar.text_input("Search Stock (e.g., RELIANCE, TCS)", "").upper().strip()

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

    if st.sidebar.button("Run Analysis"):
        with st.status("Analyzing Nifty 500 stocks...", expanded=True) as status:
            st.write("Fetching Nifty 500 list...")
            nifty500 = get_nifty500_stocks()
            if nifty500.empty:
                st.error("Failed to fetch Nifty 500 list.")
                return

            results = []
            progress_bar = st.progress(0)

            # To speed up during development/testing, we might want to limit the number of stocks
            # but for production we do all 500.
            total_stocks = len(nifty500)

            # Cache for sector data to avoid redundant downloads
            sector_cache = {}

            for i, row in nifty500.iterrows():
                symbol = row['Symbol']
                industry = row['Industry']

                progress_bar.progress((i + 1) / total_stocks, text=f"Analyzing {symbol} ({i+1}/{total_stocks})")

                # 1. Fundamental Analysis
                fundamentals = get_stock_fundamentals(symbol)
                passed_fundamentals, category = filter_fundamentals(fundamentals, roe_filter, roce_filter)

                if passed_fundamentals:
                    # 2. Technical Analysis
                    # Daily Data
                    df_daily = get_price_data(symbol, period="1y", interval="1d")
                    if df_daily.empty: continue
                    df_daily = calculate_ema(df_daily)

                    # Weekly Data
                    df_weekly = get_price_data(symbol, period="2y", interval="1wk")
                    df_weekly = calculate_ema(df_weekly)

                    patterns_found = []

                    # Pattern detection
                    if "Cup and Handle" in selected_patterns:
                        if is_cup_and_handle(df_daily) or is_cup_and_handle(df_weekly):
                            patterns_found.append("Cup and Handle")

                    if "Range Breakout" in selected_patterns:
                        if is_range_breakout(df_daily) or is_range_breakout(df_weekly):
                            patterns_found.append("Range Breakout")

                    if "Tight Setup" in selected_patterns:
                        sector_symbol = get_sector_index(industry)
                        if sector_symbol not in sector_cache:
                            sector_cache[sector_symbol] = get_sector_data(sector_symbol)

                        if is_tight_setup(df_daily, sector_cache[sector_symbol]):
                            patterns_found.append("Tight Setup")

                    if patterns_found:
                        results.append({
                            'Symbol': symbol,
                            'Industry': industry,
                            'Category': category,
                            'Patterns': ", ".join(patterns_found),
                            'ROE': fundamentals.get('ROE'),
                            'ROCE': fundamentals.get('ROCE'),
                            'df_daily': df_daily,
                            'df_weekly': df_weekly
                        })

                # Sleep briefly to avoid hitting Screener.in too hard
                time.sleep(0.1)

            status.update(label="Analysis complete!", state="complete", expanded=False)

        if not results:
            st.warning("No stocks found matching the criteria.")
        else:
            st.subheader(f"Found {len(results)} matching stocks")

            # Group results by category
            for cat in ['fii', 'dii', 'both']:
                cat_results = [r for r in results if r['Category'] == cat]
                if cat_results:
                    st.header(f"Category: {cat.upper()} increased holding")
                    for res in cat_results:
                        with st.expander(f"{res['Symbol']} - {res['Patterns']} (ROE: {res['ROE']}%, ROCE: {res['ROCE']}%)"):
                            col1, col2 = st.columns(2)
                            with col1:
                                chart_daily = create_chart(res['df_daily'], res['Symbol'], "Daily")
                                if chart_daily: st.plotly_chart(chart_daily, use_container_width=True)
                            with col2:
                                chart_weekly = create_chart(res['df_weekly'], res['Symbol'], "Weekly")
                                if chart_weekly: st.plotly_chart(chart_weekly, use_container_width=True)

if __name__ == "__main__":
    main()
